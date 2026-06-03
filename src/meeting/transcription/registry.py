"""Provider registries for the transcription module.

There are two distinct interface types here, so two separate registries:

- ``file_transcription_registry`` — for batch, file-based ASR (read a file,
  return a complete ``TranscriptionResult``). ABC: ``FileTranscriptionProvider``.
- ``realtime_transcription_registry`` — for streaming, WebSocket-style ASR
  (push audio frames in, get partial segments out). ABC:
  ``RealtimeTranscriptionProvider``.

A given backend (e.g. DashScope) can register a class in either or both,
depending on whether it supports the corresponding mode. Adapters self-register
via ``@file_transcription_registry.register(...)`` / ``@realtime_transcription_registry.register(...)``;
the factories in ``transcription/__init__.py`` look them up by name.

See ``docs/MEETING_PROVIDER_SPEC.md`` for the full adapter authoring contract.
"""

from __future__ import annotations

from src.providers.registry import ProviderRegistry

file_transcription_registry = ProviderRegistry("file_transcription")
realtime_transcription_registry = ProviderRegistry("realtime_transcription")
