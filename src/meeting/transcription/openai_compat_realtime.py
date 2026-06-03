from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

import httpx

from src.config import TranscriptionProviderConfig
from src.meeting.models import TranscriptSegment
from src.meeting.transcription.base import RealtimeTranscriptionProvider
from src.meeting.transcription.registry import realtime_transcription_registry

logger = logging.getLogger(__name__)


@realtime_transcription_registry.register("openai_compatible", display_name="OpenAI-Compatible (Realtime)")
class OpenAICompatRealtimeTranscription(RealtimeTranscriptionProvider):
    """Realtime transcription via OpenAI Realtime API WebSocket.

    Uses the OpenAI Realtime API to stream audio and receive transcription
    results in real time via WebSocket.
    """

    def __init__(self, config: TranscriptionProviderConfig):
        self._base_url = (config.base_url or "https://api.openai.com/v1").strip().rstrip("/")
        self._api_key = (config.api_key or "").strip()
        self._model = (config.model or "gpt-4o-realtime-preview").strip()
        self._ws: Any = None
        self._on_segment: Callable | None = None
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(
        self,
        on_segment: Callable[[TranscriptSegment, bool, Any], None],
        hot_words: list | None = None,
        language_hints: list[str] | None = None,
    ) -> None:
        self._on_segment = on_segment
        self._running = True

        ws_url = self._base_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url}/realtime?model={self._model}"

        headers: dict = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        headers["OpenAI-Beta"] = "realtime=v1"

        import websockets
        self._ws = await websockets.connect(ws_url, extra_headers=headers)

        # Send session config
        await self._ws.send(json.dumps({
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                "input_audio_transcription": {"model": "whisper-1"},
            },
        }))

        self._task = asyncio.create_task(self._receive_loop())

    async def send_frame(self, audio_data: bytes) -> None:
        if not self._ws or not self._running:
            return
        import base64
        encoded = base64.b64encode(audio_data).decode("ascii")
        await self._ws.send(json.dumps({
            "type": "input_audio_buffer.append",
            "audio": encoded,
        }))

    async def stop(self) -> None:
        if self._ws and self._running:
            # Commit the audio buffer so the API flushes final transcription
            try:
                await self._ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
                # Wait for final response to come through
                await asyncio.sleep(1.5)
            except Exception:
                pass
        self._running = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _receive_loop(self) -> None:
        try:
            while self._running and self._ws:
                msg = await self._ws.recv()
                event = json.loads(msg)
                evt_type = event.get("type", "")

                if evt_type == "conversation.item.input_audio_transcription.completed":
                    transcript = event.get("transcript", "")
                    if transcript and self._on_segment:
                        seg = TranscriptSegment(start=0, end=0, text=transcript)
                        self._on_segment(seg, True, None)
                elif evt_type == "response.audio_transcript.delta":
                    delta = event.get("delta", "")
                    if delta and self._on_segment:
                        seg = TranscriptSegment(start=0, end=0, text=delta)
                        self._on_segment(seg, False, None)
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.warning("Realtime transcription receive loop error", exc_info=True)
