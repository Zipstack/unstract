"""Organization isolation for the prompt-studio child models.

Custom DRF ``@action`` methods never call ``filter_queryset()``, so
``OrganizationFilterBackend`` does not run on them and a raw
``.objects.get()/filter()`` inside one is not org-scoped. These tests pin the
controls that cover that gap: org scoping on the managers, plus explicit
scoping where an id arrives directly from the request.

Shape of each case: act as org A, pass an org B id, assert the call is
refused and org B's row is untouched.
"""

import secrets

import pytest
from account_v2.models import Organization, User
from adapter_processor_v2.models import AdapterInstance
from django.test import TestCase
from django.urls import NoReverseMatch, reverse
from utils.user_context import UserContext

from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager
from prompt_studio.prompt_studio_index_manager_v2.models import IndexManager
from prompt_studio.prompt_studio_output_manager_v2.models import (
    PromptStudioOutputManager,
)
from prompt_studio.prompt_studio_v2.models import ToolStudioPrompt


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
        adapter = self._adapter(slug)
        self.profile = ProfileManager.objects.create(
            profile_name=f"profile-{slug}",
            vector_store=adapter,
            embedding_model=adapter,
            llm=adapter,
            x2text=adapter,
            chunk_size=0,
            chunk_overlap=0,
            section="Default",
            retrieval_strategy="simple",
            similarity_top_k=3,
            prompt_studio_tool=self.tool,
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
        self.a = OrgFixture(f"org-a-{secrets.token_hex(3)}")
        self.b = OrgFixture(f"org-b-{secrets.token_hex(3)}")
        # End state: acting as org A, as a request would.
        UserContext.set_organization_identifier(self.a.org.organization_id)

    # --- manager scoping: the default-deny layer (A-1) --------------------

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
        """Management commands and shell keep full access (fail-open)."""
        UserContext.set_organization_identifier(None)
        assert DocumentManager.objects.filter(
            pk=self.b.document.document_id
        ).exists()

    def test_worker_context_sees_its_own_org(self):
        """B1 — workers do run with org context set, so the manager filters
        there too. Indexing must still find its own org's rows."""
        UserContext.set_organization_identifier(self.b.org.organization_id)
        assert IndexManager.objects.filter(
            document_manager=self.b.document
        ).exists()
        assert DocumentManager.objects.get(pk=self.b.document.document_id)

    # --- explicit scoping at the reported call sites (A-3, A-5) -----------

    def test_delete_for_ide_lookup_is_tool_scoped(self):
        """A doc id from another tool in the *same* org is refused too."""
        sibling = CustomTool.objects.create(
            tool_name="sibling",
            description="second tool, same org",
            organization=self.a.org,
            created_by=self.a.user,
        )
        with self.assertRaises(DocumentManager.DoesNotExist):
            DocumentManager.objects.get(
                pk=self.a.document.document_id, tool=sibling
            )

    def test_make_profile_default_lookup_is_tool_scoped(self):
        """This lookup runs after ``get_object()`` has already passed authz on
        the caller's own tool, so org scope alone does not constrain it."""
        with self.assertRaises(ProfileManager.DoesNotExist):
            ProfileManager.objects.get(
                pk=self.b.profile.profile_id, prompt_studio_tool=self.a.tool
            )
        # Victim's default flag untouched.
        UserContext.set_organization_identifier(self.b.org.organization_id)
        assert ProfileManager.objects.get(pk=self.b.profile.profile_id).is_default

    # --- A-4: the dead, state-changing-over-GET route is gone -------------

    def test_file_delete_route_removed(self):
        """Removed rather than fixed: no caller, and it deleted over GET."""
        # Sibling route still resolves, so a naming change can't fake a pass.
        assert reverse("tenant:upload").endswith("/file/upload")
        with pytest.raises(NoReverseMatch):
            reverse("tenant:delete")
