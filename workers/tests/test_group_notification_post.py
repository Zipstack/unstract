"""The group-notification worker leg is entirely failure-path logic.

``_post_group_notification`` is the only thing standing between a transient
backend blip and a permanently unsent email, and every branch in it encodes a
different judgement about whether re-posting is safe. Two of those judgements
are easy to get backwards:

* A response the backend never sent (connect refused, DNS gone) is safe to
  re-post -- nothing happened.
* A response lost *after* the request arrived is not. The backend does not stop
  when the client disconnects, and the send path mails group by group with no
  checkpoint, so a re-post re-mails everyone who already received it.

These pin which exception lands on which side, plus the attempt cap, the
sub-500 break, and the fact that the timeout is per-phase rather than scalar --
httpx applies a scalar timeout to connect, write and read separately, so a
scalar one silently triples the task's worst-case wall time and can push it
past the queue's visibility timeout.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest
from notification.tasks import (
    _GROUP_NOTIFICATION_ATTEMPTS,
    _GROUP_NOTIFICATION_TIMEOUT,
    _post_group_notification,
    notify_group_membership_changed,
    notify_resource_shared_with_group,
)

_ENV = {
    "INTERNAL_API_BASE_URL": "http://backend/internal",
    "INTERNAL_SERVICE_API_KEY": "k",
}


def _response(status: int) -> MagicMock:
    return MagicMock(status_code=status, text="body")


class _Client:
    """Stand-in for ``httpx.Client`` that records posts and replays outcomes."""

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def __call__(self, *a, **kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        outcome = self.outcomes.pop(0) if self.outcomes else _response(200)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _run(outcomes, endpoint="resource-shared", payload=None):
    """Drive one ``_post_group_notification`` with ``outcomes`` per attempt."""
    client = _Client(outcomes)
    with (
        patch.dict("os.environ", _ENV, clear=False),
        patch("notification.tasks.httpx.Client", client),
        patch("notification.tasks.time.sleep") as sleep,
    ):
        raised = None
        try:
            _post_group_notification(endpoint, "org-a", payload or {"x": 1})
        except Exception as e:  # noqa: BLE001
            raised = e
    return client, raised, sleep


class TestRetryClassification:
    def test_success_posts_once_and_returns(self):
        client, raised, _ = _run([_response(200)])
        assert raised is None
        assert len(client.calls) == 1

    def test_server_error_exhausts_the_attempt_cap_then_raises(self):
        client, raised, sleep = _run([_response(503)] * _GROUP_NOTIFICATION_ATTEMPTS)
        assert isinstance(raised, RuntimeError)
        assert len(client.calls) == _GROUP_NOTIFICATION_ATTEMPTS
        assert sleep.call_count == _GROUP_NOTIFICATION_ATTEMPTS - 1

    def test_client_error_is_terminal_after_one_post(self):
        # A rejected payload will be rejected again; retrying only burns budget.
        client, raised, sleep = _run([_response(400)])
        assert isinstance(raised, RuntimeError)
        assert len(client.calls) == 1
        assert sleep.call_count == 0

    @pytest.mark.parametrize(
        "exc",
        [
            httpx.ReadTimeout("read"),
            httpx.WriteTimeout("write"),
            httpx.ReadError("read err"),
            httpx.RemoteProtocolError("server disconnected"),
        ],
    )
    def test_request_sent_outcome_unknown_is_never_re_posted(self, exc):
        """Each of these means the backend already has the request.

        Re-posting would re-mail every group that already succeeded, so the
        in-process attempts must end after one post.
        """
        client, raised, sleep = _run([exc])
        assert isinstance(raised, RuntimeError)
        assert len(client.calls) == 1, f"{type(exc).__name__} was re-posted"
        assert sleep.call_count == 0

    @pytest.mark.parametrize(
        "exc",
        [
            httpx.ConnectTimeout("connect"),
            httpx.ConnectError("refused"),
            httpx.PoolTimeout("pool"),
        ],
    )
    def test_request_never_left_is_retried(self, exc):
        """Nothing reached the backend, so the full attempt cap is correct."""
        client, raised, _ = _run([exc] * _GROUP_NOTIFICATION_ATTEMPTS)
        assert isinstance(raised, RuntimeError)
        assert len(client.calls) == _GROUP_NOTIFICATION_ATTEMPTS

    def test_recovers_when_a_later_attempt_succeeds(self):
        client, raised, _ = _run([_response(502), _response(200)])
        assert raised is None
        assert len(client.calls) == 2


class TestRequestShape:
    def test_missing_credentials_raise_before_any_post(self):
        client = _Client([])
        with (
            patch.dict("os.environ", {"INTERNAL_API_BASE_URL": "", "INTERNAL_SERVICE_API_KEY": ""}),
            patch("notification.tasks.httpx.Client", client),
        ):
            with pytest.raises(RuntimeError):
                _post_group_notification("resource-shared", "org-a", {})
        assert client.calls == []

    def test_url_auth_and_tenant_header(self):
        client, _, _ = _run([_response(200)], endpoint="membership-changed")
        url, kwargs = client.calls[0]
        assert url == "http://backend/internal/v1/group-notification/membership-changed/"
        assert kwargs["headers"]["Authorization"] == "Bearer k"
        # Without this the backend resolves no tenant and every org-scoped
        # query comes back empty -- a silent no-op rather than an error.
        assert kwargs["headers"]["X-Organization-ID"] == "org-a"

    def test_timeout_is_per_phase_not_scalar(self):
        """A scalar timeout is applied to connect, write AND read separately.

        Passing one would let a single post spend it three times over, which is
        what pushed this task past the consumer's visibility timeout.
        """
        client, _, _ = _run([_response(200)])
        timeout = client.calls[0][1]["timeout"]
        assert isinstance(timeout, httpx.Timeout)
        assert timeout is _GROUP_NOTIFICATION_TIMEOUT
        assert timeout.connect < timeout.read

    def test_task_wall_time_stays_under_the_visibility_timeout(self):
        """The bound the chart and compose comments defer to.

        VT is 300s for this worker in both deployments; the heartbeat is frozen
        for the task's duration, so health-stale (360s) is the other ceiling.
        """
        t = _GROUP_NOTIFICATION_TIMEOUT
        per_post = t.connect + t.write + t.read + t.pool
        worst = per_post * _GROUP_NOTIFICATION_ATTEMPTS
        assert worst < 300, f"worst case {worst}s exceeds the 300s visibility timeout"


class TestTaskPayloads:
    def test_resource_shared_task_sends_every_field_the_endpoint_requires(self):
        client = _Client([_response(200)])
        with (
            patch.dict("os.environ", _ENV, clear=False),
            patch("notification.tasks.httpx.Client", client),
        ):
            notify_resource_shared_with_group(
                group_ids=[2, 5],
                actor_id=7,
                resource_kind="workflow",
                resource_id="wf-1",
                organization_id="org-a",
                share_action="revoked",
                revoked_at="2026-01-01T00:00:00+00:00",
            )
        url, kwargs = client.calls[0]
        assert url.endswith("/resource-shared/")
        assert kwargs["json"] == {
            "group_ids": [2, 5],
            "actor_id": 7,
            "resource_kind": "workflow",
            "resource_id": "wf-1",
            "share_action": "revoked",
            "revoked_at": "2026-01-01T00:00:00+00:00",
        }

    def test_share_direction_sends_a_null_cutoff_rather_than_omitting_it(self):
        # The endpoint requires the key on both directions; omitting it is a 400.
        client = _Client([_response(200)])
        with (
            patch.dict("os.environ", _ENV, clear=False),
            patch("notification.tasks.httpx.Client", client),
        ):
            notify_resource_shared_with_group(
                group_ids=[2],
                actor_id=7,
                resource_kind="workflow",
                resource_id="wf-1",
                organization_id="org-a",
                share_action="shared",
                revoked_at=None,
            )
        assert client.calls[0][1]["json"]["revoked_at"] is None

    def test_membership_task_payload(self):
        client = _Client([_response(200)])
        with (
            patch.dict("os.environ", _ENV, clear=False),
            patch("notification.tasks.httpx.Client", client),
        ):
            notify_group_membership_changed(
                group_id=3,
                actor_id=7,
                membership_action="removed",
                user_ids=[11, 12],
                organization_id="org-a",
            )
        url, kwargs = client.calls[0]
        assert url.endswith("/membership-changed/")
        assert kwargs["json"] == {
            "group_id": 3,
            "actor_id": 7,
            "membership_action": "removed",
            "user_ids": [11, 12],
        }
