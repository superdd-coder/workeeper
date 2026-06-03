from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import httpx

from src.config import TranscriptionProviderConfig
from src.meeting.models import TranscriptSegment, TranscriptionResult
from src.meeting.transcription.base import FileTranscriptionProvider
from src.meeting.transcription.registry import file_transcription_registry

logger = logging.getLogger(__name__)


@file_transcription_registry.register("openai_compatible", display_name="OpenAI-Compatible (Whisper)")
class OpenAICompatFileTranscription(FileTranscriptionProvider):
    """File transcription via OpenAI Whisper API: POST {base_url}/audio/transcriptions."""

    SUPPORTED_LANGUAGE_HINTS = [
        {"code": "auto", "label": "Auto"},
        {"code": "zh", "label": "Chinese"},
        {"code": "en", "label": "English"},
        {"code": "ja", "label": "Japanese"},
        {"code": "ko", "label": "Korean"},
        {"code": "ms", "label": "Malay"},
        {"code": "th", "label": "Thai"},
        {"code": "id", "label": "Indonesian"},
    ]

    def __init__(self, config: TranscriptionProviderConfig):
        self._base_url = (config.base_url or "https://api.openai.com/v1").strip().rstrip("/")
        self._api_key = (config.api_key or "").strip()
        self._model = (config.model or "whisper-1").strip()

    async def transcribe(
        self,
        file_path: str,
        language_hints: list[str] | None = None,
        hot_words: list | None = None,
    ) -> TranscriptionResult:
        url = f"{self._base_url}/audio/transcriptions"

        import tempfile
        local_path = file_path
        cleanup = False

        if file_path.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.get(file_path)
                resp.raise_for_status()
                suffix = Path(file_path).suffix or ".wav"
                tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
                tmp.write(resp.content)
                tmp.close()
                local_path = tmp.name
                cleanup = True

        try:
            file_data = await asyncio.to_thread(lambda: open(local_path, "rb").read())

            suffix = Path(file_path).suffix or ".wav"
            data_fields = {
                "model": self._model,
                "response_format": "verbose_json",
            }
            if language_hints:
                data_fields["language"] = language_hints[0]
            # Whisper has no dedicated hot words API, but the prompt parameter
            # can bias recognition toward specific vocabulary.
            if hot_words:
                words = []
                for hw in hot_words:
                    t = hw.get("text", "") if isinstance(hw, dict) else getattr(hw, "text", "")
                    if t:
                        words.append(t)
                if words:
                    data_fields["prompt"] = ", ".join(words)
                    logger.info("Applying %d hot words via Whisper prompt parameter", len(words))
            files = {"file": ("audio" + suffix, file_data, "application/octet-stream")}

            async with httpx.AsyncClient(timeout=300) as client:
                headers = {}
                if self._api_key:
                    headers["Authorization"] = f"Bearer {self._api_key}"
                resp = await client.post(url, data=data_fields, files=files, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            logger.info("Whisper response keys: %s, segments count: %d",
                         list(data.keys()), len(data.get("segments", [])))

            text = data.get("text", "")
            segments = []
            for seg in data.get("segments", []):
                segments.append(TranscriptSegment(
                    start=seg.get("start", 0.0),
                    end=seg.get("end", 0.0),
                    text=seg.get("text", "").strip(),
                ))

            return TranscriptionResult(
                text=text,
                segments=segments,
                language=data.get("language"),
            )
        finally:
            if cleanup and os.path.exists(local_path):
                os.unlink(local_path)
