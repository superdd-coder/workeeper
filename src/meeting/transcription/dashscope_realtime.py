from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable

from src.config import TranscriptionProviderConfig
from src.meeting.models import TranscriptSegment
from src.meeting.transcription.base import RealtimeTranscriptionProvider
from src.meeting.transcription.registry import realtime_transcription_registry

try:
    import dashscope
    from dashscope.audio.asr import Recognition, RecognitionCallback, VocabularyService

    _HAS_DASHSCOPE = True
except ImportError:
    _HAS_DASHSCOPE = False

logger = logging.getLogger(__name__)

_DEFAULT_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
_DEFAULT_REALTIME_MODEL = "fun-asr-realtime"


def _require_dashscope() -> None:
    if not _HAS_DASHSCOPE:
        raise ImportError(
            "dashscope package is required for DashScope transcription. "
            "Install it with: pip install dashscope"
        )


@realtime_transcription_registry.register(
    "dashscope_funasr_realtime",
    display_name="DashScope FunASR (realtime)",
)
class DashScopeRealtimeTranscription(RealtimeTranscriptionProvider):
    """DashScope FunASR real-time streaming transcription via WebSocket.

    Uses the ``dashscope.audio.asr.Recognition`` class with a callback to
    deliver incremental transcription results.  Because the underlying SDK
    is synchronous/blocking, all blocking calls are offloaded to a thread
    via ``asyncio.to_thread``.
    """

    supports_hot_words = True
    SUPPORTED_LANGUAGE_HINTS = [
        {"code": "auto", "label": "Auto"},
        {"code": "zh", "label": "Chinese"},
        {"code": "en", "label": "English"},
    ]

    def __init__(self, config: TranscriptionProviderConfig):
        _require_dashscope()
        self._api_key = config.api_key
        self._model = config.model or _DEFAULT_REALTIME_MODEL
        self._base_ws_url = _DEFAULT_WS_URL
        self._recognition: Any | None = None
        self._vocab_id: str | None = None

    def _build_vocabulary_items(self, hot_words: list | None) -> list | None:
        if not hot_words:
            return None
        items = []
        for hw in hot_words:
            text = hw.get("text", "") if isinstance(hw, dict) else getattr(hw, "text", "")
            weight = hw.get("weight", 4) if isinstance(hw, dict) else getattr(hw, "weight", 4)
            lang = hw.get("lang", "") if isinstance(hw, dict) else getattr(hw, "lang", "")
            if not text:
                continue
            item = {"text": text, "weight": min(5, max(1, weight // 2 + 1))}
            if lang:
                item["lang"] = lang
            items.append(item)
        return items if items else None

    def _create_vocabulary(self, hot_words: list) -> str | None:
        vocabulary = self._build_vocabulary_items(hot_words)
        if not vocabulary:
            return None
        service = VocabularyService(api_key=self._api_key)
        prefix = f"tr{int(time.time() * 1000) % 10000000:07d}"  # max 10 chars
        logger.info("[DashScope RT] Creating vocabulary: prefix=%s model=%s words=%s",
                     prefix, self._model, vocabulary)
        try:
            vocab_id = service.create_vocabulary(
                target_model=self._model,
                prefix=prefix,
                vocabulary=vocabulary,
            )
        except Exception as exc:
            logger.error("[DashScope RT] Failed to create vocabulary: %s", exc)
            return None

        if not vocab_id:
            logger.error("[DashScope RT] Empty vocabulary_id returned")
            return None

        for _ in range(30):
            try:
                status_info = service.query_vocabulary(vocab_id)
                status = status_info[0] if isinstance(status_info, list) else status_info
                if isinstance(status, dict) and status.get("status") == "OK":
                    logger.info("[DashScope RT] Vocabulary %s ready with %d hot words", vocab_id, len(vocabulary))
                    return vocab_id
            except Exception:
                pass
            time.sleep(0.5)

        logger.error("[DashScope RT] Vocabulary %s timed out", vocab_id)
        self._delete_vocabulary(vocab_id, self._api_key)
        return None

    @staticmethod
    def _delete_vocabulary(vocab_id: str, api_key: str | None = None) -> None:
        try:
            VocabularyService(api_key=api_key).delete_vocabulary(vocab_id)
            logger.info("[DashScope RT] Deleted vocabulary %s", vocab_id)
        except Exception as exc:
            logger.warning("[DashScope RT] Failed to delete vocabulary %s: %s", vocab_id, exc)

    async def start(
        self,
        on_segment: Callable[[TranscriptSegment, bool, Any], None],
        hot_words: list | None = None,
        language_hints: list[str] | None = None,
    ) -> None:
        """Start a real-time transcription session.

        Args:
            on_segment: Called as on_segment(segment, is_final, key) for every
                        recognized chunk. ``key`` is a stable identifier
                        (sentence_id from the SDK, or a fallback) so callers
                        can deduplicate updates for the same sentence.
            hot_words: Optional list of HotWordItem dicts.
            language_hints: Optional language hints (e.g. ["zh", "en"]).
        """
        dashscope.api_key = self._api_key
        dashscope.base_websocket_api_url = self._base_ws_url

        callback = _RealtimeCallback(on_segment)
        self._recognition = Recognition(
            model=self._model,
            format="pcm",
            sample_rate=16000,
            callback=callback,
        )

        # Create cloud-side hot words vocabulary if needed
        self._vocab_id = None
        if hot_words:
            self._vocab_id = self._create_vocabulary(hot_words)
            if self._vocab_id:
                logger.info("[DashScope RT] Using vocabulary_id=%s for realtime transcription", self._vocab_id)

        start_kwargs: dict[str, Any] = {}
        if self._vocab_id:
            start_kwargs["vocabulary_id"] = self._vocab_id
        if language_hints:
            start_kwargs["language_hints"] = language_hints

        logger.info(
            "Starting realtime transcription: model=%s start_kwargs=%s",
            self._model, start_kwargs,
        )
        await asyncio.to_thread(self._recognition.start, **start_kwargs)

    async def send_frame(self, audio_data: bytes) -> None:
        """Send a raw PCM audio frame to the DashScope recognition service."""
        if self._recognition is None:
            raise RuntimeError("Transcription session not started. Call start() first.")
        await asyncio.to_thread(self._recognition.send_audio_frame, audio_data)

    async def stop(self) -> None:
        """Stop the transcription session and clean up hot words vocabulary."""
        if self._recognition is not None:
            await asyncio.to_thread(self._recognition.stop)
            self._recognition = None
            logger.info("Realtime transcription stopped")
        if self._vocab_id:
            self._delete_vocabulary(self._vocab_id, self._api_key)
            self._vocab_id = None


class _RealtimeCallback:
    """DashScope Recognition callback that forwards events to the caller.

    The SDK wraps each sentence event as:
        result.output = {"sentence": [sentence_dict]}
    where sentence_dict has: text, begin_time, end_time, speaker_id, sentence_id.
    A sentence is final when end_time is not None. The same sentence_id is
    sent multiple times as the SDK refines end_time and speaker_id.
    """

    def __init__(self, on_segment: Callable[[TranscriptSegment, bool, Any], None]):
        self._on_segment = on_segment

    def on_open(self) -> None:
        logger.debug("Realtime transcription WebSocket opened")

    def on_close(self, status_code: int = 0, status_message: str = "") -> None:
        logger.debug("Realtime transcription WebSocket closed: %s %s", status_code, status_message)

    def on_complete(self) -> None:
        logger.debug("Realtime transcription session complete")

    def on_error(self, result: Any) -> None:
        # Don't call str(result) — dashscope's __str__ can raise KeyError on
        # partial error responses. Fall back to type+repr instead.
        message = getattr(result, "message", None) or repr(result)
        logger.error("Realtime transcription error: %s", message)

    def on_event(self, result: Any) -> None:
        try:
            output = getattr(result, "output", None)
            if not output or not isinstance(output, dict):
                return

            sentence_data = output.get("sentence")
            if sentence_data is None:
                return

            # SDK wraps as {"sentence": [dict, ...]}
            sentences = sentence_data if isinstance(sentence_data, list) else [sentence_data]

            for sent in sentences:
                if not isinstance(sent, dict):
                    continue
                # Skip heartbeats
                if sent.get("heartbeat"):
                    continue

                text = (sent.get("text") or "").strip()
                if not text:
                    continue

                start_ms = float(sent.get("begin_time", 0) or 0)
                end_ms = float(sent.get("end_time", 0) or 0)
                speaker_id = sent.get("speaker_id")
                sentence_id = sent.get("sentence_id")
                # DashScope signals sentence end by having end_time set
                is_final = sent.get("end_time") is not None

                # DEBUG: log every event so we can verify the SDK actually
                # returns speaker_id when diarization is enabled.
                print(
                    f"[Realtime-Event] text={text[:60]!r} "
                    f"speaker_id={speaker_id!r} sentence_id={sentence_id!r} "
                    f"is_final={is_final} start={start_ms} end={end_ms}",
                    flush=True,
                )

                segment = TranscriptSegment(
                    start=start_ms / 1000.0,
                    end=end_ms / 1000.0,
                    text=text,
                    speaker_id=str(speaker_id) if speaker_id is not None else None,
                )
                # Use sentence_id as the unique key for this segment; falls back
                # to a hashable tuple of (start, text) when the SDK doesn't
                # provide one (older dashscope versions).
                key = sentence_id if sentence_id is not None else f"{start_ms}:{text}"
                self._on_segment(segment, is_final, key)
        except Exception:
            logger.warning("Failed to process realtime transcription event", exc_info=True)
