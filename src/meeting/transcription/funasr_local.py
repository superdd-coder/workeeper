from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from src.config import TranscriptionProviderConfig
from src.meeting.models import TranscriptSegment, TranscriptionResult
from src.meeting.transcription.base import FileTranscriptionProvider
from src.meeting.transcription.registry import file_transcription_registry

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "FunAudioLLM/SenseVoiceSmall"
_DEFAULT_VAD_MODEL = "funasr/fsmn-vad"
_DEFAULT_PUNC_MODEL = "funasr/ct-punc"
_DEFAULT_SPK_MODEL = "funasr/campplus"
_HUB = "hf"


@file_transcription_registry.register(
    "funasr_local",
    display_name="SenseVoice Small (local, 5 langs, fast)",
)
class FunASRLocalFileTranscription(FileTranscriptionProvider):
    """Local FunASR file transcription with integrated speaker diarization.

    Uses FunASR's ``AutoModel`` pipeline with VAD + punctuation + speaker
    embedding models in a single call.  The ``spk_model`` parameter enables
    built-in speaker diarization so output segments already carry
    ``speaker_id`` — no separate diarization post-processing is needed.
    """

    supports_hot_words = True
    SUPPORTED_LANGUAGE_HINTS = [
        {"code": "auto", "label": "Auto"},
        {"code": "zh", "label": "Chinese"},
        {"code": "en", "label": "English"},
        {"code": "ja", "label": "Japanese"},
        {"code": "ko", "label": "Korean"},
    ]

    def __init__(self, config: TranscriptionProviderConfig):
        from funasr import AutoModel  # lazy, optional dependency
        from src.providers.load_state import detect_device

        self._model_name = config.model or _DEFAULT_MODEL
        self._vad_model = config.vad_model or _DEFAULT_VAD_MODEL
        punc_name = config.punc_model if config.punc_model is not None else _DEFAULT_PUNC_MODEL
        self._spk_model = config.spk_model or _DEFAULT_SPK_MODEL
        self._device = (config.device if config.device and config.device != "auto" else detect_device())
        # Validate device works, fall back to auto-detection if not
        if self._device != "cpu":
            try:
                import torch
                t = torch.zeros(1, device=self._device)
                del t
            except Exception:
                logger.warning("Device '%s' not available, falling back to CPU", self._device)
                self._device = "cpu"

        model_kwargs: dict[str, Any] = {
            "model": self._model_name,
            "vad_model": self._vad_model,
            "spk_model": self._spk_model,
            "device": self._device,
            "hub": _HUB,
            "disable_update": True,
        }

        logger.info("Loading local FunASR model: %s", model_kwargs)
        try:
            self._model = AutoModel(**model_kwargs)
        except Exception:
            logger.warning(
                "Failed to load FunASR with VAD+speaker, retrying with model only: %s",
                self._model_name,
            )
            try:
                self._model = AutoModel(model=self._model_name, device=self._device, hub=_HUB, disable_update=True)
            except Exception:
                logger.error(
                    "Failed to load FunASR fallback with model only: %s",
                    self._model_name, exc_info=True,
                )
                raise
            self._spk_model = None  # No speaker diarization in fallback
        logger.info("Local FunASR model loaded")

        # Load punctuation model separately to avoid timestamp mismatch crash
        self._punc_model = None
        if punc_name:
            try:
                logger.info("Loading punctuation model: %s", punc_name)
                self._punc_model = AutoModel(model=punc_name, device=self._device, hub=_HUB, disable_update=True)
                logger.info("Punctuation model loaded")
            except Exception:
                logger.warning("Failed to load punctuation model '%s', punctuation will be skipped", punc_name, exc_info=True)

    async def transcribe(
        self,
        file_path: str,
        language_hints: list[str] | None = None,
        hot_words: list | None = None,
    ) -> TranscriptionResult:
        logger.info("Local FunASR transcription: %s", file_path)
        generate_kwargs: dict[str, Any] = {"input": file_path}
        if hot_words:
            hotword_str = " ".join(
                hw.get("text", "") if isinstance(hw, dict) else getattr(hw, "text", "")
                for hw in hot_words
            ).strip()
            if hotword_str:
                generate_kwargs["hotword"] = hotword_str
                logger.info("Applying %d hot words via FunASR local hotword", len(hot_words))
        try:
            results = await asyncio.to_thread(
                self._model.generate, **generate_kwargs,
            )
        except Exception as exc:
            raise RuntimeError(f"Local FunASR transcription failed: {exc}") from exc

        segments = self._parse_segments(results)

        # Post-process: add punctuation to each segment
        if self._punc_model and segments:
            segments = await self._add_punctuation(segments)

        full_text = " ".join(s.text for s in segments)
        logger.info(
            "Local FunASR done: %d segments, %d speakers",
            len(segments),
            len({s.speaker_id for s in segments if s.speaker_id}),
        )
        return TranscriptionResult(text=full_text, segments=segments)

    async def _add_punctuation(self, segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
        """Apply punctuation model to each segment's text."""
        def _punctuate(texts: list[str]) -> list[str]:
            results = self._punc_model.generate(input=texts)
            return [r.get("text", t) for r, t in zip(results, texts)]

        texts = [s.text for s in segments]
        try:
            punctuated = await asyncio.to_thread(_punctuate, texts)
            for seg, ptext in zip(segments, punctuated):
                seg.text = ptext
        except Exception:
            logger.warning("Punctuation post-processing failed, keeping original text", exc_info=True)
        return segments

    _SENSEVOICE_TAG_RE = re.compile(r"<\|[^|]*\|>")

    @staticmethod
    def _clean_sensevoice_tags(text: str) -> str:
        """Remove SenseVoice special tags like <|zh|>, <|NEUTRAL|>, <|BGM|>."""
        return FunASRLocalFileTranscription._SENSEVOICE_TAG_RE.sub("", text).strip()

    @staticmethod
    def _parse_segments(results: list[dict[str, Any]]) -> list[TranscriptSegment]:
        """Parse FunASR generate() output into TranscriptSegment list.

        FunASR with ``spk_model`` returns per-sentence info with speaker
        labels in the ``sentence_info`` field.  Without ``spk_model``,
        falls back to the top-level ``text`` + ``timestamp`` fields.
        """
        if not results:
            return []

        result = results[0] if isinstance(results, list) else results

        # Preferred: sentence_info with speaker diarization
        sentence_info = result.get("sentence_info")
        if sentence_info:
            segments: list[TranscriptSegment] = []
            for item in sentence_info:
                # FunASR uses "text" (punc_segment mode) or "sentence" (vad_segment mode)
                raw_text = item.get("text") or item.get("sentence") or ""
                if isinstance(raw_text, list):
                    raw_text = " ".join(raw_text)
                text = FunASRLocalFileTranscription._clean_sensevoice_tags(str(raw_text)).strip()
                if not text:
                    continue
                start_ms = item.get("start") or 0
                end_ms = item.get("end") or 0
                speaker = item.get("speaker") or item.get("spk")
                segments.append(TranscriptSegment(
                    start=float(start_ms) / 1000.0,
                    end=float(end_ms) / 1000.0,
                    text=text,
                    speaker_id=str(speaker) if speaker is not None else None,
                ))
            return segments

        # Fallback: plain text + timestamps (no speaker info)
        text = FunASRLocalFileTranscription._clean_sensevoice_tags(result.get("text") or "").strip()
        timestamps = result.get("timestamp", [])
        if not text or not timestamps:
            return []

        return [TranscriptSegment(
            start=float(timestamps[0][0]) / 1000.0,
            end=float(timestamps[-1][1]) / 1000.0,
            text=text,
            speaker_id=None,
        )]
