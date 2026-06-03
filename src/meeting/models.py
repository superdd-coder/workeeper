from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class MeetingStatus(str, Enum):
    created = "created"
    recording = "recording"
    transcribing = "transcribing"
    completed = "completed"


class MeetingMode(str, Enum):
    upload = "upload"
    record = "record"


class TranscriptSegment(BaseModel):
    start: float  # seconds
    end: float
    text: str
    speaker_id: str | None = None


class TranscriptionResult(BaseModel):
    text: str
    segments: list[TranscriptSegment] = []
    language: str | None = None


class Meeting(BaseModel):
    id: str = ""
    title: str = ""
    status: MeetingStatus = MeetingStatus.created
    mode: MeetingMode | None = None
    audio_path: str | None = None
    notes_path: str | None = None
    transcript_path: str | None = None
    detail: str | None = None
    summary: str | None = None
    todos: list[dict] | None = None
    sections: list[dict] | None = None
    transcription_error: str | None = None
    summarizing: bool = False
    allocated_collections: list[str] = Field(default_factory=list)
    allocated_file_ids: list[str] = Field(default_factory=list)
    # Old fields kept for backward-compat deserialization; excluded from output
    allocated_collection: str | None = Field(default=None, exclude=True)
    allocated_file_id: str | None = Field(default=None, exclude=True)
    speaker_names: dict[str, str] | None = None
    hot_words_library_id: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="before")
    @classmethod
    def migrate_old_fields(cls, data: dict) -> dict:
        """Migrate old singular allocation fields to new list fields."""
        if isinstance(data, dict):
            if "allocated_collection" in data and "allocated_collections" not in data:
                val = data.pop("allocated_collection")
                data["allocated_collections"] = [val] if val else []
            if "allocated_file_id" in data and "allocated_file_ids" not in data:
                val = data.pop("allocated_file_id")
                data["allocated_file_ids"] = [val] if val else []
        return data
