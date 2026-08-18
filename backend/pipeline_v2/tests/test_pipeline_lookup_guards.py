"""Both pipeline lookups must treat a malformed identifier as "not found".

``Pipeline.pk`` is a UUID column, so a non-UUID string raises Django's
``ValidationError`` out of ``to_python`` rather than ``DoesNotExist``. Left
uncaught it escapes as a 500 for what is ordinary client garbage.

This matters most on ``get_active_pipeline``, which is reached *before*
authentication: ``BaseAPIKeyValidator`` checks only that some ``Bearer`` string
is present, then ``PipelineDeploymentHelper.validate_and_process`` looks the
pipeline up and only afterwards validates the key. So an unauthenticated caller
sending any non-UUID path segment to the public execution endpoint could force a
500 with a traceback.

The real module is imported and its collaborators patched (Django is loaded by
the rig's test env), so no database is touched and these stay in the unit tier.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.exceptions import ValidationError

from pipeline_v2.models import Pipeline
from pipeline_v2.pipeline_processor import PipelineProcessor

MALFORMED_ID = "not-a-uuid"


class TestMalformedIdentifierIsNotAServerFault:
    """A non-UUID id resolves to ``None``, never an unhandled exception."""

    @pytest.mark.parametrize(
        "lookup",
        ["get_active_pipeline", "get_pipeline_by_id"],
    )
    def test_validation_error_becomes_none(self, lookup: str) -> None:
        with patch.object(
            PipelineProcessor, "fetch_pipeline", side_effect=ValidationError("bad uuid")
        ):
            assert getattr(PipelineProcessor, lookup)(MALFORMED_ID) is None

    @pytest.mark.parametrize(
        "lookup",
        ["get_active_pipeline", "get_pipeline_by_id"],
    )
    def test_absent_row_still_becomes_none(self, lookup: str) -> None:
        with patch.object(
            PipelineProcessor, "fetch_pipeline", side_effect=Pipeline.DoesNotExist
        ):
            assert getattr(PipelineProcessor, lookup)(MALFORMED_ID) is None

    @pytest.mark.parametrize(
        "lookup",
        ["get_active_pipeline", "get_pipeline_by_id"],
    )
    def test_an_unexpected_error_is_not_swallowed(self, lookup: str) -> None:
        """The catch must stay narrow -- a database outage is not a 404."""
        with patch.object(
            PipelineProcessor,
            "fetch_pipeline",
            side_effect=RuntimeError("database is down"),
        ):
            with pytest.raises(RuntimeError):
                getattr(PipelineProcessor, lookup)(MALFORMED_ID)
