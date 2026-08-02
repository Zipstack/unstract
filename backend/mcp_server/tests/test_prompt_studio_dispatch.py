"""The Prompt Studio billable tools actually deliver their payload.

These four tools were previously executed by no test — they appeared only in
registry name-lists and spend-guard assertions — which is how the dispatch bug
survived: ``_dispatch`` routed through ``PromptStudioCoreView.as_view()``, and
``as_view()`` calls ``initialize_request()``, building a *new* DRF ``Request``
with no ``_full_data``. ``.data`` then re-parsed ``request.body``, so the view
received the JSON-RPC envelope instead of ``document_id``/``prompt_id`` — and
because these tools are billable, budget was consumed before the failure.

Two things are pinned here, and they are different. The payload assertions pin
*argument construction* — that ``fetch_response`` maps ``prompt_id`` onto the
view's ``id`` field, and so on. ``test_the_action_attribute_is_set`` and
``test_get_object_is_reachable`` pin the *dispatch mechanism*, and they are the
ones that fail if the bare-instance path is missing anything DRF needs.

**These tests drive a real ``PromptStudioCoreView`` subclass, not a mock.** An
earlier version of this file patched the view class wholesale, which made every
payload assertion pass against a dispatch that raised ``AttributeError`` in
production: the actions call ``get_object()`` → ``get_queryset()``, which reads
``self.action``, and ``self.action`` is set only by ``initialize_request`` —
i.e. only by ``as_view()``. Mocking the collaborator whose behaviour is at issue
is exactly how the bug this file exists to prevent got through a green suite.

``SimpleTestCase``: ``get_object`` and the four action bodies are stubbed, so no
database is needed. What is *not* stubbed is the bare-instance setup itself —
the stub reads ``self.action`` and ``self.kwargs["pk"]`` exactly as the real
``get_object`` chain does, which is what makes the missing-attribute regression
observable. The action bodies are out of scope here; they are the delegated
view's own responsibility and are covered by its tests.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.http import Http404
from django.test import SimpleTestCase
from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory

from mcp_server.tools.prompt_studio import (
    bulk_fetch_response,
    fetch_response,
    index_document,
    single_pass_extraction,
)

PROJECT_ID = "55555555-5555-5555-5555-555555555555"
DOCUMENT_ID = "66666666-6666-6666-6666-666666666666"
PROMPT_ID = "77777777-7777-7777-7777-777777777777"
OTHER_PROMPT_ID = "99999999-9999-9999-9999-999999999999"
PROFILE_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

# What a real MCP request carries in request.data: the JSON-RPC envelope, not
# the tool's arguments. If dispatch regresses, this is what the view sees.
ENVELOPE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "indexDocument", "arguments": {"document_id": DOCUMENT_ID}},
}


class FakeProject:
    tool_id = PROJECT_ID
    tool_name = "Invoice Prompts"


def build_request(data=None):
    """A real DRF Request whose body is the JSON-RPC envelope.

    Built the way the transport builds one — the envelope really is what
    ``.data`` re-parses to if dispatch loses ``_full_data``, so a regression
    shows up as the envelope arriving at the action rather than as a mock
    quietly returning whatever it was told to.
    """
    django_request = APIRequestFactory().post(
        "/api/v1/unstract/org-mcp/mcp/",
        data=json.dumps(data if data is not None else ENVELOPE),
        content_type="application/json",
    )
    return Request(django_request, parsers=[JSONParser()])


class RecordingView(PromptStudioCoreView):
    """A real ``PromptStudioCoreView`` subclass with two things stubbed.

    ``get_object`` is overridden because the real one runs ``for_user``
    querysets and DRF filter backends that need a live DB; the four action
    bodies are replaced by ``_record`` because their real bodies dispatch Celery
    work. Neither stub is the point — both deliberately read ``self.action`` and
    ``self.kwargs["pk"]`` first, the attributes a bare instance is missing, so
    the setup ``_dispatch`` performs is exercised for real and a regression in
    it fails here exactly as it would in production.
    """

    seen: dict = {}

    def get_object(self):
        # Real get_object() → get_queryset() → `self.action == "list"`, and
        # → self.kwargs[lookup]. Touch both so a bare instance missing either
        # raises here just as it does in production.
        _ = self.action == "list"
        _ = self.kwargs["pk"]
        return FakeProject()

    def _record(self, request, pk=None):
        RecordingView.seen = {
            "payload": request.data,
            "pk": pk,
            "action": self.action,
            "project": self.get_object(),
        }
        return Response({"ok": True}, status=200)

    index_document = _record
    fetch_response = _record
    bulk_fetch_response = _record
    single_pass_extraction = _record


class PromptStudioDispatchTest(SimpleTestCase):
    def _run(self, tool, view_class=None, **kwargs):
        """Invoke a tool against a real view subclass.

        ``view_class`` swaps in a stub whose action raises, for the error-path
        tests; everything else about the dispatch is unchanged. Returns what the
        action observed alongside the tool's own result.
        """
        RecordingView.seen = {}
        request = build_request()
        self.request = request

        context = MagicMock()
        context.request = request
        context.org_name = "org-mcp"

        with (
            patch(
                "mcp_server.tools.prompt_studio._resolve_project",
                return_value=FakeProject(),
            ),
            patch(
                "mcp_server.tools.prompt_studio.PromptStudioCoreView",
                view_class or RecordingView,
            ),
        ):
            result = tool(context, project_id=PROJECT_ID, **kwargs)

        return dict(RecordingView.seen), result

    def test_index_document_delivers_document_id(self) -> None:
        seen, result = self._run(index_document, document_id=DOCUMENT_ID)

        assert seen["payload"] == {"document_id": DOCUMENT_ID}
        assert seen["payload"] != ENVELOPE, "the view received the JSON-RPC envelope"
        assert seen["pk"] == PROJECT_ID
        assert result["ok"] is True

    def test_fetch_response_delivers_prompt_and_document(self) -> None:
        seen, _ = self._run(fetch_response, document_id=DOCUMENT_ID, prompt_id=PROMPT_ID)

        # The view names this field `id`, not `prompt_id`; the mapping is the
        # kind of thing only an executed test catches.
        assert seen["payload"] == {"document_id": DOCUMENT_ID, "id": PROMPT_ID}

    def test_fetch_response_passes_optional_profile(self) -> None:
        seen, _ = self._run(
            fetch_response,
            document_id=DOCUMENT_ID,
            prompt_id=PROMPT_ID,
            profile_manager_id=PROFILE_ID,
        )

        assert seen["payload"]["profile_manager"] == PROFILE_ID

    def test_bulk_fetch_response_delivers_prompt_ids(self) -> None:
        seen, _ = self._run(
            bulk_fetch_response,
            document_id=DOCUMENT_ID,
            prompt_ids=[PROMPT_ID, OTHER_PROMPT_ID],
        )

        assert seen["payload"] == {
            "document_id": DOCUMENT_ID,
            "prompt_ids": [PROMPT_ID, OTHER_PROMPT_ID],
        }

    def test_single_pass_extraction_delivers_document_id(self) -> None:
        seen, _ = self._run(single_pass_extraction, document_id=DOCUMENT_ID)

        assert seen["payload"] == {"document_id": DOCUMENT_ID}

    def test_dispatch_restores_request_data_afterwards(self) -> None:
        """The swap is scoped to the call.

        ``_full_data`` belongs to the live request that the transport is still
        holding; leaving a tool's payload on it would corrupt anything reading
        ``request.data`` later in the same MCP call.
        """
        self._run(index_document, document_id=DOCUMENT_ID)

        assert self.request._full_data == ENVELOPE

    def test_the_action_attribute_is_set(self) -> None:
        """``self.action`` is what ``get_queryset`` branches on.

        ``ViewSetMixin.initialize_request`` normally sets it, and only
        ``as_view()`` calls that — so a bare instance without it raises
        AttributeError inside ``get_object()``. Every one of these tools calls
        ``get_object()``, and the budget is claimed before the handler runs, so
        omitting this fails all four *after* charging for them.
        """
        seen, _ = self._run(index_document, document_id=DOCUMENT_ID)

        assert seen["action"] == "index_document"

    def test_get_object_is_reachable(self) -> None:
        """The action can resolve its project — the whole DRF path works.

        This is the assertion a mocked view cannot make: it is what fails when
        `action`, `kwargs` or `request` is missing from the bare instance.
        """
        seen, _ = self._run(index_document, document_id=DOCUMENT_ID)

        assert isinstance(seen["project"], FakeProject)

    def test_dispatch_restores_request_data_after_a_failure(self) -> None:
        """Restoration is in a finally, so a raising view does not leak it."""

        class Exploding(RecordingView):
            def index_document(self, req, pk=None):
                raise RuntimeError("view exploded")

        with self.assertRaises(RuntimeError):
            self._run(index_document, view_class=Exploding, document_id=DOCUMENT_ID)

        assert self.request._full_data == ENVELOPE

    def test_a_view_refusal_is_returned_as_data(self) -> None:
        """Http404/APIException must not escape as a raw exception.

        ``dispatch()`` would have converted these to a non-2xx Response; the
        bare-instance path bypasses it. ``_result`` documents non-2xx as
        returned-as-data — the agent needs the reason to fix its next call —
        so an escaping exception would become an opaque TOOL_EXECUTION_ERROR
        with the budget already spent.
        """

        class Refusing(RecordingView):
            def index_document(self, req, pk=None):
                raise Http404

        _, result = self._run(
            index_document, view_class=Refusing, document_id=DOCUMENT_ID
        )

        assert result["ok"] is False
        assert result["status"] == 404

    def test_a_permission_denial_is_returned_as_data(self) -> None:
        """Same for check_object_permissions' PermissionDenied."""

        class Denying(RecordingView):
            def index_document(self, req, pk=None):
                raise PermissionDenied("nope")

        _, result = self._run(index_document, view_class=Denying, document_id=DOCUMENT_ID)

        assert result["ok"] is False
        assert result["status"] == 403

    def test_missing_request_is_an_agent_error(self) -> None:
        """A context with no live request refuses rather than raising."""
        from mcp_server.exceptions import MCPToolError

        context = MagicMock()
        context.request = None
        context.org_name = "org-mcp"

        with patch(
            "mcp_server.tools.prompt_studio._resolve_project",
            return_value=FakeProject(),
        ):
            with self.assertRaises(MCPToolError):
                index_document(context, project_id=PROJECT_ID, document_id=DOCUMENT_ID)

    def test_a_server_fault_is_logged_and_not_sold_as_an_argument_error(self) -> None:
        """A 5xx from the view must not read to the agent as "your fault".

        IndexingAPIError, AnswerFetchError and ExtractionAPIError are
        APIException subclasses carrying status_code 500. Catching them turned
        a genuine server fault into an ordinary tool result — with no operator
        log, and a note telling the agent to fix its arguments and try again on
        a tool that charges for every attempt.
        """
        from prompt_studio.prompt_studio_core_v2.exceptions import IndexingAPIError

        class Failing(RecordingView):
            def index_document(self, req, pk=None):
                raise IndexingAPIError("vector store unreachable")

        with patch("mcp_server.tools.prompt_studio.logger") as log:
            _, result = self._run(
                index_document, view_class=Failing, document_id=DOCUMENT_ID
            )

        assert result["status"] == 500
        assert result["ok"] is False
        # The operator signal the transport used to provide before this arm.
        # Asserted as "something was logged at error level" rather than naming
        # logger.exception: the message is routed through log_exception, which
        # deliberately uses logger.error and omits the traceback so a
        # credential in the exception text cannot reach log aggregation.
        log.error.assert_called_once()
        # And the agent is told not to retry-and-pay.
        assert "not because of your arguments" in result["note"]

    def test_a_4xx_still_reads_as_a_correctable_argument_error(self) -> None:
        """The distinction has to cut both ways, or it is just a rename."""
        from rest_framework.exceptions import ValidationError

        class Rejecting(RecordingView):
            def index_document(self, req, pk=None):
                raise ValidationError("document_id is required")

        with patch("mcp_server.tools.prompt_studio.logger") as log:
            _, result = self._run(
                index_document, view_class=Rejecting, document_id=DOCUMENT_ID
            )

        assert result["status"] == 400
        assert "usually a missing or invalid argument" in result["note"]
        log.error.assert_not_called()
        log.exception.assert_not_called()

    def test_a_malformed_document_id_is_refused_before_the_view(self) -> None:
        """Sibling ids reach the same UUID lookups the project id does.

        A Django ValidationError from `DocumentManager.objects.get(pk=...)` is
        neither APIException nor Http404, so it would escape as an opaque
        failure with the budget already spent.
        """
        from mcp_server.exceptions import MCPToolError

        with self.assertRaises(MCPToolError) as caught:
            self._run(index_document, document_id="not-a-uuid")

        assert "not a valid document id" in str(caught.exception)

    def test_a_malformed_prompt_id_is_refused(self) -> None:
        from mcp_server.exceptions import MCPToolError

        with self.assertRaises(MCPToolError):
            self._run(fetch_response, document_id=DOCUMENT_ID, prompt_id="oops")

    def test_a_malformed_id_in_prompt_ids_is_refused(self) -> None:
        """BulkFetchResponse takes a list, so each element needs the guard."""
        from mcp_server.exceptions import MCPToolError

        with self.assertRaises(MCPToolError):
            self._run(
                bulk_fetch_response,
                document_id=DOCUMENT_ID,
                prompt_ids=[PROMPT_ID, "not-a-uuid"],
            )
