from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from src.config import TranscriptionProviderConfig
from src.meeting.models import TranscriptSegment, TranscriptionResult
from src.meeting.transcription.base import FileTranscriptionProvider
from src.meeting.transcription.registry import file_transcription_registry

try:
    import dashscope
    from dashscope.audio.asr import Transcription, VocabularyService

    _HAS_DASHSCOPE = True
except ImportError:
    _HAS_DASHSCOPE = False

logger = logging.getLogger(__name__)

_DEFAULT_HTTP_URL = "https://dashscope.aliyuncs.com/api/v1"
_DEFAULT_WS_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
_DEFAULT_FILE_MODEL = "fun-asr"
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 2.0  # seconds


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if an exception indicates a rate limit (HTTP 429)."""
    msg = str(exc).lower()
    return "429" in msg or "throttling" in msg or "ratequota" in msg or "rate_quota" in msg


def _retry_with_backoff(fn, description: str = "API call"):
    """Call fn() with exponential backoff on rate limit errors."""
    last_exc = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if not _is_rate_limit_error(exc) or attempt >= _MAX_RETRIES:
                raise
            delay = _RETRY_BASE_DELAY ** attempt
            logger.warning(
                "[DashScope] Rate limit on %s (attempt %d/%d), retrying in %.1fs...",
                description, attempt, _MAX_RETRIES, delay,
            )
            time.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _require_dashscope() -> None:
    if not _HAS_DASHSCOPE:
        raise ImportError(
            "dashscope package is required for DashScope transcription. "
            "Install it with: pip install dashscope"
        )


@file_transcription_registry.register(
    "dashscope_funasr",
    display_name="DashScope FunASR (file)",
)
class DashScopeFileTranscription(FileTranscriptionProvider):
    """DashScope FunASR file-based transcription with speaker diarization.

    Uploads local audio files to DashScope OSS, then uses the batch
    Transcription API with speaker diarization support.
    For HTTP(S) URLs, uses the async Transcription API directly.
    """

    supports_hot_words = True
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
        _require_dashscope()
        self._api_key = config.api_key
        self._model = config.model or _DEFAULT_FILE_MODEL
        self._ws_url = _DEFAULT_WS_URL
        self._http_url = _DEFAULT_HTTP_URL

    def _build_vocabulary_items(self, hot_words: list | None) -> list | None:
        """Convert HotWordItem list to DashScope vocabulary format (weight 1-5)."""
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
        """Create a cloud-side hot words vocabulary and return its ID.

        DashScope requires creating a vocabulary first, then passing its ID
        as ``phrase_id`` to the transcription call. Returns None on failure.
        """
        vocabulary = self._build_vocabulary_items(hot_words)
        if not vocabulary:
            return None

        service = VocabularyService(api_key=self._api_key)
        prefix = f"tr{int(time.time() * 1000) % 10000000:07d}"  # max 10 chars
        logger.info("[DashScope] Creating vocabulary: prefix=%s model=%s words=%s",
                     prefix, self._model, vocabulary)
        try:
            vocab_id = service.create_vocabulary(
                target_model=self._model,
                prefix=prefix,
                vocabulary=vocabulary,
            )
        except Exception as exc:
            logger.error("[DashScope] Failed to create vocabulary: %s", exc)
            return None

        # create_vocabulary returns the vocab_id string directly
        if not vocab_id:
            logger.error("[DashScope] Empty vocabulary_id returned")
            return None

        # Poll until status is OK
        for _ in range(30):
            try:
                full_response = service.query_vocabulary(vocab_id)
                status = full_response[0] if isinstance(full_response, list) else full_response
                logger.info("[DashScope] Query vocab %s response: %s", vocab_id, full_response)
                if isinstance(status, dict) and status.get("status") == "OK":
                        # Wait extra time for propagation
                        time.sleep(2)
                        logger.info("[DashScope] Vocabulary %s ready with %d hot words", vocab_id, len(vocabulary))
                        return vocab_id
            except Exception as exc:
                logger.warning("[DashScope] Query vocabulary %s failed: %s", vocab_id, exc)
            time.sleep(0.5)

        logger.error("[DashScope] Vocabulary %s timed out waiting for OK status", vocab_id)
        self._delete_vocabulary(vocab_id, self._api_key)
        return None

    @staticmethod
    def _delete_vocabulary(vocab_id: str, api_key: str | None = None) -> None:
        """Delete a cloud-side hot words vocabulary to free quota (max 10 per account)."""
        try:
            VocabularyService(api_key=api_key).delete_vocabulary(vocab_id)
            logger.info("[DashScope] Deleted vocabulary %s", vocab_id)
        except Exception as exc:
            logger.warning("[DashScope] Failed to delete vocabulary %s: %s", vocab_id, exc)

    async def transcribe(
        self,
        file_path: str,
        language_hints: list[str] | None = None,
        hot_words: list | None = None,
    ) -> TranscriptionResult:
        """Transcribe an audio file.

        For local files, uploads to DashScope OSS then uses batch Transcription API.
        For HTTP(S) URLs, uses the async Transcription API directly.
        Both paths support speaker diarization.
        """
        if file_path.startswith(("http://", "https://")):
            result = await asyncio.to_thread(
                self._transcribe_from_url, file_path, language_hints, hot_words
            )
        else:
            result = await asyncio.to_thread(
                self._transcribe_local_file, file_path, language_hints, hot_words
            )
        return result

    # -- Local file via upload + batch Transcription API --------------------

    def _transcribe_local_file(
        self,
        file_path: str,
        language_hints: list[str] | None,
        hot_words: list | None = None,
    ) -> TranscriptionResult:
        """Upload local file to DashScope OSS, then use batch Transcription API for speaker diarization."""
        from dashscope import Files
        dashscope.api_key = self._api_key
        file_id = None

        try:
            # 1. Upload file to DashScope (with retry for rate limits)
            logger.info("Uploading local file to DashScope: %s", file_path)
            upload_result = _retry_with_backoff(
                lambda: Files.upload(file_path=file_path, purpose="inference"),
                description="file upload",
            )
            if upload_result.status_code != 200:
                raise RuntimeError(f"DashScope file upload failed: {upload_result}")
            file_id = upload_result.output["uploaded_files"][0]["file_id"]
            logger.info("File uploaded, file_id=%s", file_id)

            # 2. Get signed OSS URL
            file_info = Files.get(file_id=file_id)
            oss_url = file_info.output["url"]
            logger.info("Got OSS URL for file")

            # 3. Use batch Transcription API with OSS URL
            return self._transcribe_from_url(oss_url, language_hints, hot_words)
        finally:
            # 4. Clean up: delete uploaded file from DashScope
            if file_id:
                try:
                    Files.delete(file_id=file_id)
                    logger.info("Deleted uploaded file from DashScope: %s", file_id)
                except Exception:
                    logger.warning("Failed to delete uploaded file: %s", file_id)

    # -- URL-based via async Transcription API (fallback) ------------------

    def _transcribe_from_url(
        self,
        file_url: str,
        language_hints: list[str] | None,
        hot_words: list | None = None,
    ) -> TranscriptionResult:
        """Transcribe via async Transcription API (requires public URL)."""
        dashscope.api_key = self._api_key
        dashscope.base_http_api_url = self._http_url

        vocab_id = None
        if hot_words:
            vocab_id = self._create_vocabulary(hot_words)

        try:
            kwargs: dict[str, Any] = {
                "model": self._model,
                "file_urls": [file_url],
                "diarization_enabled": True,
            }
            if language_hints:
                kwargs["language_hints"] = language_hints
            if vocab_id:
                kwargs["vocabulary_id"] = vocab_id
                logger.info("[DashScope] Using vocabulary_id=%s for URL transcription", vocab_id)

            logger.info("Submitting URL-based transcription: model=%s url=%s", self._model, file_url)
            task_response = _retry_with_backoff(
                lambda: Transcription.async_call(**kwargs),
                description="transcription submit",
            )
            if task_response.output is None:
                raise RuntimeError(
                    f"Transcription async_call returned null output. "
                    f"status_code={task_response.status_code} code={task_response.code} "
                    f"message={task_response.message} kwargs_keys={list(kwargs.keys())}"
                )
            task_id = task_response.output.get("task_id")
            logger.info("Transcription task submitted: task_id=%s", task_id)

            logger.info("Waiting for transcription task %s to complete (polling every 5s)...", task_id)
            while True:
                time.sleep(5)
                status_response = Transcription.fetch(task=task_id)
                if status_response.output is None:
                    logger.error("Transcription task %s returned null output: %s", task_id, status_response)
                    raise RuntimeError(f"Transcription task {task_id} returned null output")
                task_status = status_response.output.get("task_status")
                logger.info("Transcription task %s status: %s", task_id, task_status)
                if task_status == "FAILED":
                    raise RuntimeError(f"Transcription task {task_id} FAILED")
                if task_status == "SUCCEEDED":
                    break
            output = status_response.output
            logger.info("Transcription task %s completed, output keys: %s", task_id, list(output.keys()) if isinstance(output, dict) else type(output))

            transcription_urls = output.get("results", []) if isinstance(output, dict) else []
            segments: list[TranscriptSegment] = []

            for entry in transcription_urls:
                url = entry.get("transcription_url")
                if not url:
                    logger.warning("No transcription_url in entry: %s", entry)
                    continue
                try:
                    parsed = self._fetch_and_parse_segments(url)
                    logger.info("Fetched %d segments from %s", len(parsed), url[:80])
                    segments.extend(parsed)
                except Exception:
                    logger.warning("Failed to fetch transcription result from %s", url, exc_info=True)

            full_text = " ".join(s.text for s in segments)
            logger.info("URL transcription done: %d segments, %d chars", len(segments), len(full_text))
            return TranscriptionResult(text=full_text, segments=segments)
        finally:
            if vocab_id:
                self._delete_vocabulary(vocab_id, self._api_key)

    @staticmethod
    def _fetch_and_parse_segments(url: str) -> list[TranscriptSegment]:
        """Download the transcription JSON from DashScope and parse segments.

        DashScope returns ``transcripts[]``, each containing a ``sentences``
        array with ``text``, ``begin_time``, ``end_time``, and ``speaker_id``.
        """
        resp = httpx.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        segments: list[TranscriptSegment] = []
        for transcript in data.get("transcripts", []):
            sentences = transcript.get("sentences", [])
            for item in sentences:
                text = (item.get("text") or "").strip()
                if not text:
                    continue
                segments.append(
                    TranscriptSegment(
                        start=float(item.get("begin_time", 0)) / 1000.0,  # ms -> s
                        end=float(item.get("end_time", 0)) / 1000.0,
                        text=text,
                        speaker_id=str(item.get("speaker_id")) if item.get("speaker_id") is not None else None,
                    )
                )
        return segments
