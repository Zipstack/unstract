"""Tests for ``InternalAPIClient.agent_kv_stage_report`` (Agent-KV cloud
executor Task 2) and the worker package's dependency on
``unstract-agent-kv-schema``.

Mirrors ``workers/tests/test_agent_kv_scheduler_tasks.py``'s
``TestInternalClientAgentKvMethods`` pattern for patching the client's HTTP
layer: ``patch.object(InternalAPIClient, "post", ...)`` plus
``InternalAPIClient.__new__(InternalAPIClient)`` to avoid running the real
``__init__`` (session/config setup unrelated to this method).
"""

from unittest.mock import patch

from shared.api import InternalAPIClient


class TestAgentKvStageReport:
    def test_posts_minimal_body_to_the_stage_endpoint(self):
        """seconds/counters are omitted from the body when not provided."""
        with patch.object(
            InternalAPIClient, "post", return_value={"ok": True}
        ) as m_post:
            client = InternalAPIClient.__new__(InternalAPIClient)
            result = client.agent_kv_stage_report(
                "job-1", "org-1", "extract", "started"
            )

        m_post.assert_called_once_with(
            "v1/agent-kv/jobs/job-1/stage/",
            data={"org_id": "org-1", "stage": "extract", "status": "started"},
            organization_id="org-1",
        )
        assert result == {"ok": True}

    def test_posts_full_body_with_seconds_and_counters(self):
        with patch.object(
            InternalAPIClient, "post", return_value={"ok": True}
        ) as m_post:
            client = InternalAPIClient.__new__(InternalAPIClient)
            result = client.agent_kv_stage_report(
                "job-2",
                "org-2",
                "extract",
                "completed",
                seconds=1.5,
                counters={"rows": 3},
            )

        m_post.assert_called_once_with(
            "v1/agent-kv/jobs/job-2/stage/",
            data={
                "org_id": "org-2",
                "stage": "extract",
                "status": "completed",
                "seconds": 1.5,
                "counters": {"rows": 3},
            },
            organization_id="org-2",
        )
        assert result == {"ok": True}

    def test_returns_the_parsed_noop_response_for_a_terminal_job(self):
        """The backend answers {"ok": true, "noop": true} for a terminal job;
        the client returns it unchanged (idempotent, no special-casing).
        """
        with patch.object(
            InternalAPIClient, "post", return_value={"ok": True, "noop": True}
        ):
            client = InternalAPIClient.__new__(InternalAPIClient)
            result = client.agent_kv_stage_report(
                "job-3", "org-3", "extract", "started"
            )

        assert result == {"ok": True, "noop": True}

    def test_empty_counters_dict_is_omitted_like_none(self):
        """``if counters:`` (not ``is not None``) mirrors the brief's
        implementation exactly -- an empty dict is falsy and left out.
        """
        with patch.object(
            InternalAPIClient, "post", return_value={"ok": True}
        ) as m_post:
            client = InternalAPIClient.__new__(InternalAPIClient)
            client.agent_kv_stage_report(
                "job-4", "org-4", "extract", "started", counters={}
            )

        m_post.assert_called_once_with(
            "v1/agent-kv/jobs/job-4/stage/",
            data={"org_id": "org-4", "stage": "extract", "status": "started"},
            organization_id="org-4",
        )


class TestAgentKvSchemaImport:
    def test_agent_kv_schema_package_importable(self):
        """The worker venv depends on unstract-agent-kv-schema (path dependency,
        editable) so the schema compiler is importable inside worker code.
        """
        import unstract.agent_kv_schema  # noqa: F401
