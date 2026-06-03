"""TDD tests for meeting service: project splitting, recommendation, multi-allocation.

Covers:
- Summary prompt project-grouping support
- split_by_project() parsing and service flow
- recommend_collections() with mocked embeddings
- allocate_to_multiple_collections() flow
- New routes for split, recommend, and allocate-multi

Run: python -m pytest tests/test_meeting_split.py -x -v
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import numpy as np
import pytest

from src.meeting.models import Meeting, MeetingStatus


# ── Helpers ───────────────────────────────────────────────────


def _make_meeting(**overrides) -> Meeting:
    defaults = dict(
        id="abc123",
        title="Test Meeting",
        status=MeetingStatus.completed,
        detail="Some detail",
        summary="Some summary",
        todos=[{"text": "Todo 1"}],
        created_at=datetime(2026, 6, 3, 10, 0, 0),
        updated_at=datetime(2026, 6, 3, 10, 0, 0),
    )
    defaults.update(overrides)
    return Meeting(**defaults)


# ═══════════════════════════════════════════════════════════════
# 1. Summary Parser — PROJECT Sub-Sections
# ═══════════════════════════════════════════════════════════════


class TestParseSummaryWithProjects:
    """Tests for _parse_summary_response handling ===PROJECT:Name=== sub-sections."""

    def test_parse_single_project_in_detail(self):
        """Parser extracts project-grouped detail when PROJECT sections exist."""
        from src.meeting.service import _parse_summary_response

        raw = (
            "===TITLE===\nMulti-project Meeting\n\n"
            "===DETAIL===\n"
            "===PROJECT:Project A===\n"
            "Detail for project A.\n\n"
            "===PROJECT:Project B===\n"
            "Detail for project B.\n\n"
            "===SUMMARY===\nOverall summary.\n\n"
            '===TODO===\n[{"text": "Task 1"}]'
        )
        title, detail, summary, todos, sections = _parse_summary_response(raw)

        assert title == "Multi-project Meeting"
        assert "Project A" in detail
        assert "Project B" in detail
        assert summary == "Overall summary."
        assert len(todos) == 1

    def test_parse_project_sections_in_multiple_main_sections(self):
        """Parser handles PROJECT sub-sections in DETAIL, SUMMARY, and TODO."""
        from src.meeting.service import _parse_summary_response

        raw = (
            "===TITLE===\nTwo Projects\n\n"
            "===DETAIL===\n"
            "===PROJECT:Alpha===\nAlpha detail.\n"
            "===PROJECT:Beta===\nBeta detail.\n\n"
            "===SUMMARY===\n"
            "===PROJECT:Alpha===\nAlpha summary.\n"
            "===PROJECT:Beta===\nBeta summary.\n\n"
            "===TODO===\n"
            "===PROJECT:Alpha===\n[{\"text\": \"Alpha task\"}]\n"
            "===PROJECT:Beta===\n[{\"text\": \"Beta task\"}]\n"
        )
        title, detail, summary, todos, sections = _parse_summary_response(raw)

        assert title == "Two Projects"
        # detail should contain project info
        assert "Alpha" in detail
        assert "Beta" in detail
        # todos should accumulate from both project sections
        assert len(todos) == 2

    def test_parse_no_project_sections_unchanged(self):
        """Parser works normally when no PROJECT sub-sections exist."""
        from src.meeting.service import _parse_summary_response

        raw = (
            "===TITLE===\nSimple Meeting\n\n"
            "===DETAIL===\nSimple detail.\n\n"
            "===SUMMARY===\nSimple summary.\n\n"
            '===TODO===\n[{"text": "Task 1"}]'
        )
        title, detail, summary, todos, sections = _parse_summary_response(raw)

        assert title == "Simple Meeting"
        assert detail == "Simple detail."
        assert summary == "Simple summary."
        assert len(todos) == 1


# ═══════════════════════════════════════════════════════════════
# 2. split_by_project Service Tests
# ═══════════════════════════════════════════════════════════════


class TestSplitByProjectService:
    """split_by_project() on MeetingService — reads structured sections."""

    def test_split_by_project_uses_sections(self):
        """split_by_project returns projects from meeting.sections."""
        from src.meeting.service import MeetingService

        meeting = _make_meeting(
            sections=[
                {"heading": "Alpha", "summary": "Alpha summary",
                 "detail": "Alpha detail", "todos": [{"text": "Alpha task"}]},
                {"heading": "Beta", "summary": "Beta summary",
                 "detail": "Beta detail", "todos": [{"text": "Beta task"}]},
            ],
        )

        with patch("src.meeting.service.store") as mock_store:
            mock_store.get_meeting.return_value = meeting
            svc = MeetingService()
            result = asyncio.get_event_loop().run_until_complete(
                svc.split_by_project("abc123")
            )

        assert len(result) == 2
        assert result[0]["name"] == "Alpha"
        assert result[1]["name"] == "Beta"

    def test_split_by_project_fallback_single_project(self):
        """split_by_project falls back to single project when no sections."""
        from src.meeting.service import MeetingService

        meeting = _make_meeting(
            title="2026-01-01 10:00 Project X",
            detail="Discussion about X.",
            summary="Summary of X.",
            todos=[{"text": "X task"}],
        )

        with patch("src.meeting.service.store") as mock_store:
            mock_store.get_meeting.return_value = meeting
            svc = MeetingService()
            result = asyncio.get_event_loop().run_until_complete(
                svc.split_by_project("abc123")
            )

        assert len(result) == 1
        assert "Project X" in result[0]["name"]

    def test_split_by_project_meeting_not_found(self):
        """split_by_project raises FileNotFoundError for missing meeting."""
        from src.meeting.service import MeetingService

        with patch("src.meeting.service.store") as mock_store:
            mock_store.get_meeting.return_value = None
            svc = MeetingService()

            with pytest.raises(FileNotFoundError):
                asyncio.get_event_loop().run_until_complete(
                    svc.split_by_project("missing")
                )

    def test_split_by_project_no_content(self):
        """split_by_project raises ValueError when meeting has no content."""
        from src.meeting.service import MeetingService

        meeting = _make_meeting(detail=None, summary=None, todos=None)

        with patch("src.meeting.service.store") as mock_store:
            mock_store.get_meeting.return_value = meeting
            svc = MeetingService()

            with pytest.raises(ValueError, match="no content"):
                asyncio.get_event_loop().run_until_complete(
                    svc.split_by_project("abc123")
                )


# ═══════════════════════════════════════════════════════════════
# 4. recommend_collections Tests
# ═══════════════════════════════════════════════════════════════


class TestRecommendCollections:
    """recommend_collections() with mocked embeddings."""

    def test_recommend_returns_sorted_by_similarity(self):
        """recommend_collections returns reranker-scored results sorted by score."""
        from src.meeting.service import MeetingService

        meeting = _make_meeting()

        mock_transcript = MagicMock()
        mock_transcript.text = "We discussed Project Alpha's new API design."

        with patch("src.meeting.service.store") as mock_store, \
             patch("src.meeting.service.services") as mock_services, \
             patch.object(MeetingService, '_get_collection_docs') as mock_get_docs:
            mock_store.get_meeting.return_value = meeting
            mock_store.get_transcript.return_value = mock_transcript
            mock_services.embedding = MagicMock()
            mock_services.embedding.dimensions = 3
            mock_services.reranker_provider = MagicMock()
            mock_services.reranker_provider.rerank.return_value = [
                (2, 0.95), (0, 0.85), (1, 0.30)
            ]
            # ── _get_collection_docs return value ──
            mock_get_docs.return_value = (
                ["col-alpha", "col-beta", "col-gamma"],
                [
                    "col-alpha: API docs",
                    "col-beta: ML pipeline",
                    "col-gamma: Deployment guide",
                ],
            )

            svc = MeetingService()
            result = asyncio.get_event_loop().run_until_complete(
                svc.recommend_collections("abc123")
            )

        # Sorted by score descending
        assert len(result) == 3
        assert result[0]["score"] > result[-1]["score"]
        # col-gamma (idx 2) scored highest → first result
        assert result[0]["collection"] == "col-gamma"
        # col-beta (idx 1) scored lowest → last result
        assert result[-1]["collection"] == "col-beta"

    def test_recommend_meeting_not_found(self):
        """recommend_collections raises FileNotFoundError for missing meeting."""
        from src.meeting.service import MeetingService

        with patch("src.meeting.service.store") as mock_store:
            mock_store.get_meeting.return_value = None
            svc = MeetingService()

            with pytest.raises(FileNotFoundError):
                asyncio.get_event_loop().run_until_complete(
                    svc.recommend_collections("missing")
                )

    def test_recommend_no_collections(self):
        """recommend_collections returns empty list when no collections exist."""
        from src.meeting.service import MeetingService

        meeting = _make_meeting()

        with patch("src.meeting.service.store") as mock_store, \
             patch("src.meeting.service.services") as mock_services, \
             patch.object(MeetingService, '_get_collection_docs', return_value=([], [])):
            mock_store.get_meeting.return_value = meeting
            mock_services.embedding = MagicMock()
            mock_services.embedding.dimensions = 3
            mock_services.reranker_provider = MagicMock()

            svc = MeetingService()
            result = asyncio.get_event_loop().run_until_complete(
                svc.recommend_collections("abc123")
            )

        assert result == []

    def test_recommend_no_meeting_text(self):
        """recommend_collections returns empty when meeting has no detail."""
        from src.meeting.service import MeetingService

        meeting = _make_meeting(detail=None)

        with patch("src.meeting.service.store") as mock_store, \
             patch("src.meeting.service.services") as mock_services:
            mock_store.get_meeting.return_value = meeting
            mock_services.embedding = MagicMock()
            mock_services.embedding.dimensions = 3

            svc = MeetingService()
            result = asyncio.get_event_loop().run_until_complete(
                svc.recommend_collections("abc123")
            )

        assert result == []


# ═══════════════════════════════════════════════════════════════
# 5. allocate_to_multiple_collections Tests
# ═══════════════════════════════════════════════════════════════


class TestAllocateToMultipleCollections:
    """allocate_to_multiple_collections() on MeetingService."""

    def test_allocate_multi_success(self):
        """allocate_to_multiple_collections allocates to each collection."""
        from src.meeting.service import MeetingService

        meeting = _make_meeting()
        allocations = [
            {"collection": "col-alpha", "content": "# Alpha\n\nAlpha content"},
            {"collection": "col-beta", "content": "# Beta\n\nBeta content"},
        ]
        upload_result = {"chunks_count": 3}

        with patch("src.meeting.service.store") as mock_store, \
             patch("src.meeting.service.services") as mock_services, \
             patch("src.tasks.handlers.upload_handler", new_callable=AsyncMock, return_value=upload_result) as mock_upload, \
             patch("src.meeting.service.UPLOAD_DIR", Path("/tmp/test_uploads")), \
             patch.object(Path, "write_text"):
            mock_store.get_meeting.return_value = meeting
            mock_store.update_meeting.return_value = meeting
            mock_services.db = MagicMock()

            svc = MeetingService()
            result = asyncio.get_event_loop().run_until_complete(
                svc.allocate_to_multiple_collections("abc123", allocations)
            )

        assert len(result) == 2
        assert mock_upload.call_count == 2

    def test_allocate_multi_tracks_allocations(self):
        """allocate_to_multiple_collections tracks all allocations in meeting metadata."""
        from src.meeting.service import MeetingService

        meeting = _make_meeting()
        allocations = [
            {"collection": "col-a", "content": "# A"},
            {"collection": "col-b", "content": "# B"},
        ]
        upload_result = {"chunks_count": 2}

        with patch("src.meeting.service.store") as mock_store, \
             patch("src.meeting.service.services") as mock_services, \
             patch("src.tasks.handlers.upload_handler", new_callable=AsyncMock, return_value=upload_result), \
             patch("src.meeting.service.UPLOAD_DIR", Path("/tmp/test_uploads")), \
             patch.object(Path, "write_text"):
            mock_store.get_meeting.return_value = meeting
            mock_store.update_meeting.return_value = meeting
            mock_services.db = MagicMock()

            svc = MeetingService()
            asyncio.get_event_loop().run_until_complete(
                svc.allocate_to_multiple_collections("abc123", allocations)
            )

        # Check that update_meeting was called with both allocations tracked
        update_calls = mock_store.update_meeting.call_args_list
        final_update = update_calls[-1]
        assert final_update[1]["allocated_collections"] == ["col-a", "col-b"]
        assert len(final_update[1]["allocated_file_ids"]) == 2

    def test_allocate_multi_meeting_not_found(self):
        """allocate_to_multiple_collections raises FileNotFoundError for missing meeting."""
        from src.meeting.service import MeetingService

        with patch("src.meeting.service.store") as mock_store:
            mock_store.get_meeting.return_value = None
            svc = MeetingService()

            with pytest.raises(FileNotFoundError):
                asyncio.get_event_loop().run_until_complete(
                    svc.allocate_to_multiple_collections("missing", [])
                )

    def test_allocate_multi_empty_allocations(self):
        """allocate_to_multiple_collections raises ValueError for empty allocations."""
        from src.meeting.service import MeetingService

        meeting = _make_meeting()

        with patch("src.meeting.service.store") as mock_store:
            mock_store.get_meeting.return_value = meeting
            svc = MeetingService()

            with pytest.raises(ValueError, match="empty"):
                asyncio.get_event_loop().run_until_complete(
                    svc.allocate_to_multiple_collections("abc123", [])
                )


# ═══════════════════════════════════════════════════════════════
# 6. Route Tests
# ═══════════════════════════════════════════════════════════════


class TestNewMeetingRoutes:
    """New route handlers: split-by-project, recommend-collections, allocate-multi."""

    def test_split_by_project_route(self):
        """POST /meetings/{id}/split-by-project delegates to service."""
        from src.meeting.routes import split_meeting_by_project

        with patch("src.meeting.routes.meeting_service") as mock_svc:
            mock_svc.split_by_project = AsyncMock(return_value=[
                {"name": "Alpha", "summary": "A", "detail": "D", "todos": []},
            ])

            result = asyncio.get_event_loop().run_until_complete(
                split_meeting_by_project("abc123")
            )

        assert "projects" in result
        assert len(result["projects"]) == 1
        assert result["projects"][0]["name"] == "Alpha"

    def test_recommend_collections_route(self):
        """GET /meetings/{id}/recommend-collections delegates to service."""
        from src.meeting.routes import recommend_collections

        with patch("src.meeting.routes.meeting_service") as mock_svc:
            mock_svc.recommend_collections = AsyncMock(return_value=[
                {"collection": "col-a", "score": 0.95},
                {"collection": "col-b", "score": 0.3},
            ])

            result = asyncio.get_event_loop().run_until_complete(
                recommend_collections("abc123")
            )

        assert "recommendations" in result
        assert len(result["recommendations"]) == 2
        assert result["recommendations"][0]["score"] == 0.95

    def test_allocate_multi_route(self):
        """POST /meetings/{id}/allocate-multi delegates to service."""
        from src.meeting.routes import allocate_multi

        with patch("src.meeting.routes.meeting_service") as mock_svc:
            mock_svc.allocate_to_multiple_collections = AsyncMock(return_value=[
                {"collection": "col-a", "chunks": 3},
            ])

            result = asyncio.get_event_loop().run_until_complete(
                allocate_multi(
                    "abc123",
                    {"allocations": [{"collection": "col-a", "content": "# A"}]},
                )
            )

        assert len(result) == 1
        mock_svc.allocate_to_multiple_collections.assert_called_once_with(
            "abc123", [{"collection": "col-a", "content": "# A"}]
        )

    def test_allocate_multi_route_no_body(self):
        """POST /meetings/{id}/allocate-multi handles missing allocations field."""
        from src.meeting.routes import allocate_multi

        with patch("src.meeting.routes.meeting_service") as mock_svc:
            mock_svc.allocate_to_multiple_collections = AsyncMock(return_value=[])

            result = asyncio.get_event_loop().run_until_complete(
                allocate_multi("abc123", {})
            )

        mock_svc.allocate_to_multiple_collections.assert_called_once_with("abc123", [])
