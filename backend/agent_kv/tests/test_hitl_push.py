"""The review-queue push: when it happens, when it does not, and what it never does.

The queue itself lives in a cloud app that is absent here, so the plugin is
mocked -- which is the point: these pin the SEAM's behaviour, including the
OSS-deployment case where the app genuinely is not installed.
"""

import logging
import os
from unittest import mock

import django
import pytest
from django.apps import apps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.test")
if not apps.ready:
    django.setup()

from agent_kv import hitl  # noqa: E402


class _Org:
    organization_id = "org_abc123"


def _job(queue="high-value-invoices", **over):
    job = mock.MagicMock()
    job.id = "11111111-2222-3333-4444-555555555555"
    job.hitl_queue_name = queue
    job.organization = _Org()
    job.extractor = "kv"
    job.custom_data = {"vendor": "Acme"}
    job.tags = ["q4"]
    for k, v in over.items():
        setattr(job, k, v)
    return job


@pytest.fixture
def hitl_on(settings):
    """HITL enabled, the state a submit that named a queue was accepted under."""
    settings.AGENT_KV_HITL_ENABLED = True


#: What the review app actually returns. A `MagicMock` would satisfy
#: `.get("queue_class")` with a truthy mock and drive a row UPDATE with it,
#: so every plugin double here returns the real shape.
_RESERVED_CLASS = "9f1d7c3e-55aa-5e8b-9d21-6c4b0f2a7e13"


def _plugin(returns=None):
    plugin = mock.MagicMock()
    plugin.enqueue_api_record.return_value = (
        {
            "queue_name": f"review_queue_org_abc123_{_RESERVED_CLASS}:q",
            "queue_class": _RESERVED_CLASS,
        }
        if returns is None
        else returns
    )
    return plugin


@pytest.fixture(autouse=True)
def _rows():
    """Stands in for the job table, so the echo's UPDATE is observable."""
    with mock.patch.object(hitl, "AgentKVJob") as rows:
        yield rows


@pytest.fixture(autouse=True)
def _reset_once_per_process_log():
    # The missing-plugin message is deliberately once per process; without
    # this, whichever test ran first would be the only one that sees it.
    hitl._MISSING_LOGGED.clear()
    yield
    hitl._MISSING_LOGGED.clear()


@pytest.mark.usefixtures("hitl_on")
class TestPushHappens:
    def test_enqueues_with_the_queue_the_caller_named(self):
        plugin = _plugin()
        with mock.patch.object(hitl, "_review_plugin", return_value=plugin):
            assert hitl.push_completed_job(_job(), {"fields": {"total": 1}}) is True

        kw = plugin.enqueue_api_record.call_args.kwargs
        assert kw["hitl_queue_name"] == "high-value-invoices"
        assert kw["organization_id"] == "org_abc123"
        # Deliberately NOT passed. This seam naming the queue class is the
        # defect that made a read match any workflow's records in the org: the
        # class has to be a resolvable workflow id, which only the review app
        # can supply. Asserting its ABSENCE is the regression guard.
        assert "queue_class" not in kw
        assert kw["queue_type"] == "api"
        assert kw["source_id"] == "11111111-2222-3333-4444-555555555555"
        assert kw["document_data"] == {"fields": {"total": 1}}

    def test_the_reviewer_gets_the_callers_context(self):
        plugin = _plugin()
        with mock.patch.object(hitl, "_review_plugin", return_value=plugin):
            hitl.push_completed_job(_job(), {})
        meta = plugin.enqueue_api_record.call_args.kwargs["metadata"]
        assert meta["source"] == "agentic-extract"
        assert meta["extractor"] == "kv"
        assert meta["custom_data"] == {"vendor": "Acme"}
        assert meta["tags"] == ["q4"]

    def test_an_empty_result_still_pushes(self):
        # A completed job with nothing extracted is exactly the case a human
        # should see, so this must not be optimised away.
        plugin = _plugin()
        with mock.patch.object(hitl, "_review_plugin", return_value=plugin):
            assert hitl.push_completed_job(_job(), {}) is True
        assert plugin.enqueue_api_record.call_args.kwargs["document_data"] == {}


@pytest.mark.usefixtures("hitl_on")
class TestPushDoesNotHappen:
    @pytest.mark.parametrize("queue", ["", None, "   "])
    def test_no_queue_named_is_a_silent_no_op(self, queue):
        plugin = mock.MagicMock()
        with mock.patch.object(hitl, "_review_plugin", return_value=plugin):
            assert hitl.push_completed_job(_job(queue=queue), {}) is False
        plugin.enqueue_api_record.assert_not_called()

    def test_flag_turned_off_between_submit_and_finalize_is_logged(
        self, caplog, settings
    ):
        settings.AGENT_KV_HITL_ENABLED = False
        plugin = mock.MagicMock()
        with (
            caplog.at_level(logging.WARNING),
            mock.patch.object(hitl, "_review_plugin", return_value=plugin),
        ):
            assert hitl.push_completed_job(_job(), {}) is False
        plugin.enqueue_api_record.assert_not_called()
        # The caller was promised a review by a 202 that validated, so a
        # silent drop here is the one thing this must not do.
        assert "no review record was created" in caplog.text

    def test_an_oss_deployment_without_the_app_logs_once_per_process(self, caplog):
        with (
            caplog.at_level(logging.ERROR),
            mock.patch.object(hitl, "_review_plugin", return_value=None),
        ):
            assert hitl.push_completed_job(_job(), {}) is False
            assert hitl.push_completed_job(_job(), {}) is False
            assert hitl.push_completed_job(_job(), {}) is False

        # Once, not three times: an unguarded line here is one ERROR per
        # request into Sentry, which is the fault `_CAPS_LOGGED` exists for.
        assert caplog.text.count("manual review app is not installed") == 1


@pytest.mark.usefixtures("hitl_on")
class TestPushNeverFailsTheJob:
    def test_an_enqueue_exception_is_swallowed_and_logged_with_the_queue(self, caplog):
        plugin = mock.MagicMock()
        plugin.enqueue_api_record.side_effect = RuntimeError("queue is down")

        with (
            caplog.at_level(logging.ERROR),
            mock.patch.object(hitl, "_review_plugin", return_value=plugin),
        ):
            # The extraction is stored and billed by now. Raising here would
            # turn a paid-for result into `success: false`.
            assert hitl.push_completed_job(_job(), {"fields": {}}) is False

        assert "failed to push job" in caplog.text
        # The queue name is what a manual requeue needs.
        assert "high-value-invoices" in caplog.text

    def test_a_failure_while_BUILDING_the_record_does_not_escape(self, caplog):
        """Not just a failing enqueue: everything that reads off the job is
        inside the same guard, so a surprise there is swallowed too.

        A real class rather than a MagicMock, because patching a property onto
        `type(MagicMock())` sets it on the shared class and the raise never
        reaches this call.
        """

        class _BrokenJob:
            id = "11111111-2222-3333-4444-555555555555"
            hitl_queue_name = "high-value-invoices"
            extractor = "kv"
            custom_data = None
            tags = None

            @property
            def organization(self):
                raise AttributeError("organization is not loaded")

        plugin = mock.MagicMock()
        with (
            caplog.at_level(logging.ERROR),
            mock.patch.object(hitl, "_review_plugin", return_value=plugin),
        ):
            assert hitl.push_completed_job(_BrokenJob(), {}) is False
        plugin.enqueue_api_record.assert_not_called()
        assert "failed to push job" in caplog.text


class TestPluginProbe:
    """What the probe does, pinned WITHOUT depending on the deployment.

    An earlier version of this asserted `_review_plugin() is None` outright,
    reasoning that the review app is a cloud app and therefore absent. That
    holds in the OSS repo's own CI and is false in the merged tree the cloud
    repo's `ci-test.yaml` builds (OSS checkout + cloud plugins copied in),
    where `pluggable_apps.manual_review_v2` imports fine -- so the test
    asserted the test ENVIRONMENT, passed in one lane and failed in the other,
    and told you nothing about the probe either way.
    """

    def test_an_absent_app_resolves_to_none_rather_than_raising(self):
        # `None` in `sys.modules` makes `import` raise ImportError, which is
        # the OSS deployment's condition reproduced rather than assumed.
        with mock.patch.dict("sys.modules", {"pluggable_apps.manual_review_v2": None}):
            assert hitl._review_plugin() is None

    def test_a_present_app_resolves_to_the_push_module(self):
        # The other half, and the one that actually exercises the cross-repo
        # seam: a deployment WITH the review app must find
        # `agentic_extract_push`, by that exact name, or every push silently
        # does nothing (the caller swallows the failure by design).
        stub = mock.MagicMock()
        with mock.patch.dict(
            "sys.modules",
            {
                "pluggable_apps.manual_review_v2": mock.MagicMock(
                    agentic_extract_push=stub
                ),
                "pluggable_apps.manual_review_v2.agentic_extract_push": stub,
            },
        ):
            assert hitl._review_plugin() is stub


@pytest.mark.usefixtures("hitl_on")
class TestTheReadBackCoordinateIsRecorded:
    """The class the review app assigned is stored, because only it knows one.

    `hitl_queue_class` is the `{class}` segment of the approved-results
    endpoint. The API caller cannot derive it -- it is a workflow id the review
    app owns -- so if it is not echoed, the documented way to read reviewed
    data back has no address to call.
    """

    def test_the_class_the_app_returned_is_written_to_this_job_only(self, _rows):
        job = _job()
        with mock.patch.object(hitl, "_review_plugin", return_value=_plugin()):
            assert hitl.push_completed_job(job, {}) is True

        # A narrow UPDATE on this row, not `job.save()`: the finalize path has
        # already written the row through `mark_terminal` and holds a stale
        # copy, so a full save would write its other fields back.
        _rows.objects.filter.assert_called_once_with(id=job.id)
        _rows.objects.filter.return_value.update.assert_called_once_with(
            hitl_queue_class=_RESERVED_CLASS
        )
        # Also on the instance, so the response built from it in this same
        # request can echo the coordinate rather than waiting for a reload.
        assert job.hitl_queue_class == _RESERVED_CLASS

    def test_a_return_value_without_the_class_writes_nothing(self, _rows):
        """No guess, no placeholder, and still a successful push.

        An older review app that returns only the queue name must not produce
        an invented class -- a caller would send it and get someone else's
        records or none. The push itself still happened, so it still reports
        True.
        """
        plugin = _plugin(returns={"queue_name": "review_queue_org_abc123_x:q"})
        with mock.patch.object(hitl, "_review_plugin", return_value=plugin):
            assert hitl.push_completed_job(_job(), {}) is True

        _rows.objects.filter.assert_not_called()

    def test_a_push_that_failed_records_no_class(self, _rows):
        plugin = _plugin()
        plugin.enqueue_api_record.side_effect = RuntimeError("queue is down")
        with mock.patch.object(hitl, "_review_plugin", return_value=plugin):
            assert hitl.push_completed_job(_job(), {}) is False

        _rows.objects.filter.assert_not_called()
