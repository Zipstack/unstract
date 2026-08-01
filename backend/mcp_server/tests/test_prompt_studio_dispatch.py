"""The Prompt Studio billable tools actually deliver their payload.

These four tools were previously executed by no test — they appeared only in
registry name-lists and spend-guard assertions — which is how the dispatch bug
survived: ``_dispatch`` routed through ``PromptStudioCoreView.as_view()``, and
``as_view()`` calls ``initialize_request()``, building a *new* DRF ``Request``
with no ``_full_data``. ``.data`` then re-parsed ``request.body``, so the view
received the JSON-RPC envelope instead of ``document_id``/``prompt_id`` — and
because these tools are billable, budget was consumed before the failure.

The assertion that matters is on the payload the delegated action received.
A test that only checked the tool returned a dict would have passed throughout.

``SimpleTestCase``: the view and the project lookup are both patched, so no
database is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from mcp_server.tools.prompt_studio import (
    bulk_fetch_response,
    fetch_response,
    index_document,
    single_pass_extraction,
)

PROJECT_ID = "55555555-5555-5555-5555-555555555555"
DOCUMENT_ID = "66666666-6666-6666-6666-666666666666"
PROMPT_ID = "77777777-7777-7777-7777-777777777777"

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


class PromptStudioDispatchTest(SimpleTestCase):
    def _run(self, tool, **kwargs):
        """Invoke a tool with the view and project lookup stubbed.

        Returns the payload the delegated action was called with, read off
        ``request.data`` *at call time* — dispatch restores the original in a
        ``finally``, so reading it afterwards would always show the envelope
        and the assertion would be vacuous.
        """
        request = MagicMock()
        request._full_data = ENVELOPE
        request.data = ENVELOPE

        seen: dict = {}

        def capture(req, pk=None):
            # request.data is a property on the real DRF Request backed by
            # _full_data; the mock needs the two kept in step by hand.
            seen["payload"] = request._full_data
            seen["pk"] = pk
            response = MagicMock()
            response.status_code = 200
            response.data = {"ok": True}
            return response

        context = MagicMock()
        context.request = request
        context.org_name = "org-mcp"

        with (
            patch(
                "mcp_server.tools.prompt_studio._resolve_project",
                return_value=FakeProject(),
            ),
            patch("mcp_server.tools.prompt_studio.PromptStudioCoreView") as view_cls,
        ):
            view_cls.return_value = MagicMock()
            for action in (
                "index_document",
                "fetch_response",
                "bulk_fetch_response",
                "single_pass_extraction",
            ):
                setattr(view_cls.return_value, action, capture)
            result = tool(context, project_id=PROJECT_ID, **kwargs)

        self.request = request
        return seen, result

    def test_index_document_delivers_document_id(self) -> None:
        seen, result = self._run(index_document, document_id=DOCUMENT_ID)

        assert seen["payload"] == {"document_id": DOCUMENT_ID}
        assert seen["payload"] != ENVELOPE, "the view received the JSON-RPC envelope"
        assert seen["pk"] == PROJECT_ID
        assert result["ok"] is True

    def test_fetch_response_delivers_prompt_and_document(self) -> None:
        seen, _ = self._run(
            fetch_response, document_id=DOCUMENT_ID, prompt_id=PROMPT_ID
        )

        # The view names this field `id`, not `prompt_id`; the mapping is the
        # kind of thing only an executed test catches.
        assert seen["payload"] == {"document_id": DOCUMENT_ID, "id": PROMPT_ID}

    def test_fetch_response_passes_optional_profile(self) -> None:
        seen, _ = self._run(
            fetch_response,
            document_id=DOCUMENT_ID,
            prompt_id=PROMPT_ID,
            profile_manager_id="profile-1",
        )

        assert seen["payload"]["profile_manager"] == "profile-1"

    def test_bulk_fetch_response_delivers_prompt_ids(self) -> None:
        seen, _ = self._run(
            bulk_fetch_response,
            document_id=DOCUMENT_ID,
            prompt_ids=[PROMPT_ID, "other"],
        )

        assert seen["payload"] == {
            "document_id": DOCUMENT_ID,
            "prompt_ids": [PROMPT_ID, "other"],
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

    def test_dispatch_restores_request_data_after_a_failure(self) -> None:
        """Restoration is in a finally, so a raising view does not leak it."""
        request = MagicMock()
        request._full_data = ENVELOPE
        request.data = ENVELOPE
        context = MagicMock()
        context.request = request
        context.org_name = "org-mcp"

        def boom(req, pk=None):
            raise RuntimeError("view exploded")

        with (
            patch(
                "mcp_server.tools.prompt_studio._resolve_project",
                return_value=FakeProject(),
            ),
            patch("mcp_server.tools.prompt_studio.PromptStudioCoreView") as view_cls,
        ):
            view_cls.return_value = MagicMock()
            view_cls.return_value.index_document = boom
            with self.assertRaises(RuntimeError):
                index_document(
                    context, project_id=PROJECT_ID, document_id=DOCUMENT_ID
                )

        assert request._full_data == ENVELOPE

    def test_dispatch_does_not_use_as_view(self) -> None:
        """as_view() is the bug: it rebuilds the request and drops _full_data.

        Pinned explicitly because the payload assertions above would keep
        passing under a mock that made as_view() behave, while production
        would resume failing.
        """
        request = MagicMock()
        request._full_data = ENVELOPE
        request.data = ENVELOPE
        context = MagicMock()
        context.request = request
        context.org_name = "org-mcp"

        with (
            patch(
                "mcp_server.tools.prompt_studio._resolve_project",
                return_value=FakeProject(),
            ),
            patch("mcp_server.tools.prompt_studio.PromptStudioCoreView") as view_cls,
        ):
            response = MagicMock()
            response.status_code = 200
            response.data = {}
            view_cls.return_value.index_document = MagicMock(return_value=response)

            index_document(context, project_id=PROJECT_ID, document_id=DOCUMENT_ID)

        view_cls.as_view.assert_not_called()

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
                index_document(
                    context, project_id=PROJECT_ID, document_id=DOCUMENT_ID
                )
