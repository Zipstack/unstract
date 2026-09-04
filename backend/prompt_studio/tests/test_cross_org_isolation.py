"""Organization isolation for the prompt-studio child models.

``OrganizationFilterBackend`` only scopes querysets routed through
``filter_queryset()``. A raw ``.objects.get()/filter()`` written inside a view
bypasses it — including inside a custom DRF ``@action``, where
``self.get_object()`` *is* filtered but the hand-written queries beside it are
not. These tests pin the controls that cover that gap: org scoping on the
managers, plus explicit scoping where an id arrives directly from the request.

Shape of each case: act as org A, pass an org B id, assert the call is
refused and org B's row is untouched.
"""

import secrets
from unittest.mock import patch

import pytest
from account_v2.models import Organization, User
from adapter_processor_v2.models import AdapterInstance
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from permissions.roles import ResourceRole
from rest_framework.test import APIRequestFactory, force_authenticate
from tenant_account_v2.models import ResourceMembership
from utils.user_context import UserContext

from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_core_v2.views import PromptStudioCoreView
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager
from prompt_studio.prompt_studio_index_manager_v2.models import IndexManager
from prompt_studio.prompt_studio_output_manager_v2.models import (
    PromptStudioOutputManager,
)
from prompt_studio.prompt_studio_output_manager_v2.views import PromptStudioOutputView
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt


def _make_profile(name, tool, adapter, *, is_default, created_by) -> ProfileManager:
    """A ProfileManager with the fields none of these tests vary.

    Only the name, tool, adapter and default flag ever differ between call
    sites; spelling out the other nine each time hid that.
    """
    return ProfileManager.objects.create(
        profile_name=name,
        vector_store=adapter,
        embedding_model=adapter,
        llm=adapter,
        x2text=adapter,
        chunk_size=0,
        chunk_overlap=0,
        section="Default",
        retrieval_strategy="simple",
        similarity_top_k=3,
        prompt_studio_tool=tool,
        is_default=is_default,
        created_by=created_by,
    )


class OrgFixture:
    """One organization with a fully populated prompt-studio object graph."""

    def __init__(self, slug: str):
        self.org = Organization.objects.create(
            name=slug, display_name=slug, organization_id=slug
        )
        UserContext.set_organization_identifier(slug)

        self.user = User.objects.create_user(
            username=f"{slug}@example.com",
            email=f"{slug}@example.com",
            password=secrets.token_urlsafe(),
        )
        self.tool = CustomTool.objects.create(
            tool_name=f"tool-{slug}",
            description="isolation test tool",
            organization=self.org,
            created_by=self.user,
        )
        self.adapter = self._adapter(slug)
        self.profile = _make_profile(
            f"profile-{slug}",
            self.tool,
            self.adapter,
            is_default=True,
            created_by=self.user,
        )
        self.document = DocumentManager.objects.create(
            document_name=f"doc-{slug}.pdf", tool=self.tool, created_by=self.user
        )
        self.index = IndexManager.objects.create(
            document_manager=self.document, profile_manager=self.profile
        )
        self.prompt = ToolStudioPrompt.objects.create(
            prompt_key=f"key_{slug}", prompt="extract", tool_id=self.tool
        )
        self.output = PromptStudioOutputManager.objects.create(
            output="secret",
            prompt_id=self.prompt,
            document_manager=self.document,
            profile_manager=self.profile,
            tool_id=self.tool,
        )

    def _adapter(self, slug: str) -> AdapterInstance:
        return AdapterInstance.objects.create(
            adapter_name=f"adapter-{slug}",
            adapter_id="openai|test",
            adapter_type="LLM",
            adapter_metadata={},
            organization=self.org,
            created_by=self.user,
        )


@pytest.mark.django_db
class CrossOrgIsolationTest(TestCase):
    """Org A must not reach org B's prompt-studio rows through any manager."""

    def setUp(self) -> None:
        # Registered before anything can raise, and not in tearDown: UserContext
        # is thread-local, so TestCase's transaction rollback does not clear it,
        # and unittest skips tearDown when setUp fails. OrgFixture sets the
        # identifier as its second statement and then makes eight create()
        # calls, any of which can raise — without this the worker process would
        # keep an identifier pointing at a rolled-back organization and quietly
        # change manager behaviour for every later test.
        self.addCleanup(UserContext.set_organization_identifier, None)
        self.a = OrgFixture(f"org-a-{secrets.token_hex(3)}")
        self.b = OrgFixture(f"org-b-{secrets.token_hex(3)}")
        # End state: acting as org A, as a request would.
        UserContext.set_organization_identifier(self.a.org.organization_id)

    # --- manager scoping: the default-deny layer ---------------------------

    def test_document_of_other_org_is_not_gettable(self):
        """A document id from another org must not resolve."""
        with self.assertRaises(DocumentManager.DoesNotExist):
            DocumentManager.objects.get(pk=self.b.document.document_id)

    def test_prompt_of_other_org_is_not_listable(self):
        """Prompts must not be listable by another org's tool id."""
        assert not ToolStudioPrompt.objects.filter(tool_id=self.b.tool).exists()

    def test_output_of_other_org_is_not_listable(self):
        assert not PromptStudioOutputManager.objects.filter(
            tool_id=self.b.tool
        ).exists()

    def test_index_of_other_org_is_not_listable(self):
        assert not IndexManager.objects.filter(
            document_manager=self.b.document
        ).exists()

    def test_profile_of_other_org_is_not_gettable(self):
        """``make_profile_default`` takes this id straight from the body."""
        with self.assertRaises(ProfileManager.DoesNotExist):
            ProfileManager.objects.get(pk=self.b.profile.profile_id)

    # --- same-org access must still work ----------------------------------

    def test_own_org_rows_remain_visible(self):
        assert DocumentManager.objects.get(pk=self.a.document.document_id)
        assert ProfileManager.objects.get(pk=self.a.profile.profile_id)
        assert ToolStudioPrompt.objects.filter(tool_id=self.a.tool).exists()
        assert PromptStudioOutputManager.objects.filter(tool_id=self.a.tool).exists()
        assert IndexManager.objects.filter(document_manager=self.a.document).exists()

    def test_no_org_context_is_unfiltered(self):
        """Management commands and shell keep full access (fail-open).

        Pinned deliberately: no identifier means no request to take one from,
        which is a different state from the one below.
        """
        UserContext.set_organization_identifier(None)
        assert DocumentManager.objects.filter(
            pk=self.b.document.document_id
        ).exists()

    def test_unresolvable_org_context_is_empty(self):
        """An identifier that resolves to no row must not fall back to open.

        ``UserContext.get_organization()`` flattens three states to ``None``:
        no identifier, ``Organization.DoesNotExist`` and ``ProgrammingError``.
        The last two happen inside a request, so treating them like the first
        one would serve every organization's rows to a caller whose own
        organization could not be looked up.
        """
        UserContext.set_organization_identifier("org-that-does-not-exist")
        assert not DocumentManager.objects.filter(
            pk=self.b.document.document_id
        ).exists()
        assert not DocumentManager.objects.exists()

    def test_worker_context_sees_its_own_org(self):
        """Workers do run with org context set, so the manager filters there
        too. Indexing must still find its own org's rows."""
        UserContext.set_organization_identifier(self.b.org.organization_id)
        assert IndexManager.objects.filter(
            document_manager=self.b.document
        ).exists()
        assert DocumentManager.objects.get(pk=self.b.document.document_id)

    # --- explicit scoping in delete_for_ide and make_profile_default ------

    def _sibling_tool_in_org_a(self):
        """A second tool in org A, with its own default profile and document.

        Org scope cannot distinguish these from ``self.a.tool``'s own rows, so
        they are what makes the per-tool predicates observable. A cross-org id
        would 404 on org scope alone and pass even with the predicate removed.
        """
        tool = CustomTool.objects.create(
            tool_name=f"sibling-{secrets.token_hex(3)}",
            description="second tool, same org",
            organization=self.a.org,
            created_by=self.a.user,
        )
        profile = _make_profile(
            f"sibling-profile-{secrets.token_hex(3)}",
            tool,
            self.a.adapter,
            is_default=True,
            created_by=self.a.user,
        )
        document = DocumentManager.objects.create(
            document_name=f"sibling-{secrets.token_hex(3)}.pdf",
            tool=tool,
            created_by=self.a.user,
        )
        return tool, profile, document

    def _grant_owner(self, tool) -> None:
        """The OWNER row the create *view* writes.

        ``CustomTool.objects.for_user`` resolves visibility through
        ResourceMembership; the fixtures build rows directly, so without this
        ``get_object()`` 404s before the code under test runs.
        """
        ResourceMembership.objects.get_or_create(
            user=self.a.user,
            role=ResourceRole.OWNER,
            content_type=ContentType.objects.get_for_model(CustomTool),
            object_id=str(tool.tool_id),
        )

    def _delete_for_ide(self, tool, document_id):
        """DELETE prompt-studio/file/<tool> as the owner of ``tool``."""
        self._grant_owner(tool)
        view = PromptStudioCoreView.as_view({"delete": "delete_for_ide"})
        request = APIRequestFactory().delete(
            f"/prompt-studio/file/{tool.tool_id}",
            {"document_id": str(document_id)},
            format="json",
        )
        # The view reads the org off the session; the factory builds a bare
        # request, so nothing else populates it.
        request.session = {"organization": self.a.org.organization_id}
        force_authenticate(request, user=self.a.user)
        return view(request, pk=str(tool.tool_id))

    def test_make_profile_default_refuses_a_sibling_tool_profile(self):
        """Same org, different tool: org scope cannot catch this one.

        Driven through the view because the control is the ``prompt_studio_tool``
        predicate on the lookup, not anything the ORM does on its own. Removing
        that predicate lets the owner of one tool flip another tool's default
        profile within the same organization.
        """
        sibling_tool, sibling_profile, _ = self._sibling_tool_in_org_a()

        response = self._make_profile_default(self.a.tool, sibling_profile.profile_id)

        assert response.status_code == 404, response.data
        sibling_profile.refresh_from_db()
        assert sibling_profile.is_default, "sibling tool's default was altered"
        assert (
            ProfileManager.objects.filter(
                prompt_studio_tool=sibling_tool, is_default=True
            ).count()
            == 1
        )

    def test_delete_for_ide_refuses_a_sibling_tool_document(self):
        """Same org, different tool: the ``tool=`` predicate is the only guard.

        Without it the lookup is a bare pk fetch, which both deletes another
        tool's document and raises an unhandled ``DoesNotExist`` (500) when the
        id is unknown.
        """
        _, _, sibling_document = self._sibling_tool_in_org_a()

        response = self._delete_for_ide(self.a.tool, sibling_document.document_id)

        # The row is what the predicate protects: get_object_or_404 above runs
        # before either delete, so a missing predicate is what would let this
        # row be removed at all.
        assert DocumentManager.objects.filter(
            pk=sibling_document.document_id
        ).exists(), "sibling tool's document was deleted"
        assert response.status_code == 404, getattr(response, "data", response)

    # --- the ordering fix, driven through the view ------------------------

    def _make_profile_default(self, tool, profile_id):
        """PATCH make_profile_default as the owner of ``tool``."""
        self._grant_owner(tool)
        view = PromptStudioCoreView.as_view({"patch": "make_profile_default"})
        request = APIRequestFactory().patch(
            f"/prompt-studio/{tool.tool_id}/make_profile_default",
            {"default_profile": str(profile_id)},
            format="json",
        )
        force_authenticate(request, user=self.a.user)
        return view(request, pk=str(tool.tool_id))

    def _second_profile_on_tool_a(self):
        return _make_profile(
            "profile-a-second",
            self.a.tool,
            self.a.adapter,
            is_default=False,
            created_by=self.a.user,
        )

    def test_make_profile_default_switches_the_default(self):
        """The allow path: the old default is cleared and the new one set."""
        second = self._second_profile_on_tool_a()

        response = self._make_profile_default(self.a.tool, second.profile_id)

        assert response.status_code == 200, response.data
        self.a.profile.refresh_from_db()
        second.refresh_from_db()
        assert second.is_default
        assert not self.a.profile.is_default

    def test_rejected_default_leaves_the_existing_default_intact(self):
        """A non-matching id must not clear the tool's current default.

        Driven through the view on purpose: the de-dup update runs against
        every profile on the tool, and an ORM-only test never executes it, so
        it cannot observe this property at all.

        What actually guards the invariant is resolving and clearing under one
        of two conditions — resolve first, or clear first but inside the
        transaction, where the 404 rolls the clear back. Mutation-tested: this
        fails (0 defaults left) only on clear-first *without* the transaction,
        which is what the code did before. Reverting just the ordering, with
        ``transaction.atomic()`` still in place, is genuinely safe and does not
        fail here.
        """
        self._second_profile_on_tool_a()
        assert ProfileManager.objects.get(pk=self.a.profile.profile_id).is_default

        response = self._make_profile_default(self.a.tool, self.b.profile.profile_id)

        assert response.status_code == 404, response.data
        assert (
            ProfileManager.objects.filter(
                prompt_studio_tool=self.a.tool, is_default=True
            ).count()
            == 1
        ), "the tool lost (or duplicated) its default while rejecting another org's id"
        self.a.profile.refresh_from_db()
        assert self.a.profile.is_default

    # --- ProfileManager.for_user: sharing must not widen the org scope -----

    def _profile_ids_for_user(self, user):
        return {str(p.profile_id) for p in ProfileManager.objects.for_user(user)}

    def test_for_user_excludes_another_org_even_when_shared_to_org(self):
        """``for_user`` dropped its explicit tool-org filter and now leans
        entirely on ``get_queryset()``. ``shared_to_org=True`` is the branch
        that would otherwise match every organization's rows at once.
        """
        self.b.profile.shared_to_org = True
        self.b.profile.save(update_fields=["shared_to_org"])

        visible = self._profile_ids_for_user(self.a.user)

        assert str(self.a.profile.profile_id) in visible
        assert str(self.b.profile.profile_id) not in visible

    def test_for_user_service_account_branch_is_still_org_scoped(self):
        """``self.all()`` is not ``_base_manager.all()`` — it inherits the
        scope. A branch rewritten to bypass ``self`` would fail here."""
        self.a.user.is_service_account = True

        visible = self._profile_ids_for_user(self.a.user)

        assert str(self.a.profile.profile_id) in visible
        assert str(self.b.profile.profile_id) not in visible

    def test_for_user_org_admin_branch_is_still_org_scoped(self):
        """Admin of org A is not admin of every org."""
        with patch(
            "prompt_studio.prompt_profile_manager_v2.models."
            "OrganizationMemberService.is_user_organization_admin",
            return_value=True,
        ):
            visible = self._profile_ids_for_user(self.a.user)

        assert str(self.a.profile.profile_id) in visible
        assert str(self.b.profile.profile_id) not in visible

    # --- the output read endpoints, against real cross-org ids -------------

    def _output_view(self, action: str, params: dict):
        view = PromptStudioOutputView.as_view({"get": action})
        request = APIRequestFactory().get("/prompt-studio/output", params)
        force_authenticate(request, user=self.a.user)
        return view(request)

    def test_latest_outputs_by_keys_refuses_another_orgs_tool(self):
        """A real org-B tool id, not just an unmatched UUID.

        The 400 cases already covered only prove the id is parsed. This is what
        pins the scoping: org B's prompt key exists and holds a real output, so
        an unscoped query would return it.
        """
        response = self._output_view(
            "latest_outputs_by_keys",
            {"tool_id": str(self.b.tool.tool_id), "prompt_keys": self.b.prompt.prompt_key},
        )

        assert response.status_code == 200, response.data
        assert response.data == {}

    def test_latest_outputs_by_keys_still_returns_own_output(self):
        """Without this, a query scoped to nothing would pass above."""
        response = self._output_view(
            "latest_outputs_by_keys",
            {"tool_id": str(self.a.tool.tool_id), "prompt_keys": self.a.prompt.prompt_key},
        )

        assert response.status_code == 200, response.data
        assert response.data == {self.a.prompt.prompt_key: "secret"}

    def test_get_output_for_tool_default_refuses_another_orgs_ids(self):
        response = self._output_view(
            "get_output_for_tool_default",
            {
                "tool_id": str(self.b.tool.tool_id),
                "document_manager": str(self.b.document.document_id),
            },
        )

        assert response.status_code == 200, response.data
        assert response.data == {}

    # --- the dead, state-changing-over-GET route is gone -------------------

    def test_file_delete_route_removed(self):
        """Removed rather than fixed: no caller, and it deleted over GET."""
        # Sibling route still resolves, so a naming change can't fake a pass.
        assert reverse("tenant:upload").endswith("/file/upload")
        with pytest.raises(NoReverseMatch):
            reverse("tenant:delete")
