"""Size, pages and per-profile index state on the prompt-document list."""

from __future__ import annotations

import io
import json
import secrets
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pypdfium2 as pdfium
from account_v2.models import Organization, User
from adapter_processor_v2.models import AdapterInstance
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate
from utils.user_context import UserContext

from prompt_studio.prompt_profile_manager_v2.models import ProfileManager
from prompt_studio.prompt_studio_core_v2 import internal_views
from prompt_studio.prompt_studio_core_v2 import views as core_views
from prompt_studio.prompt_studio_core_v2.exceptions import IndexingAPIError
from prompt_studio.prompt_studio_core_v2.models import CustomTool
from prompt_studio.prompt_studio_core_v2.prompt_studio_helper import PromptStudioHelper
from prompt_studio.prompt_studio_document_manager_v2.models import DocumentManager
from prompt_studio.prompt_studio_document_manager_v2.serializers import (
    PromptStudioDocumentManagerSerializer,
    PromptStudioDocumentStatusSerializer,
)
from prompt_studio.prompt_studio_document_manager_v2.views import (
    PromptStudioDocumentManagerView,
)
from prompt_studio.prompt_studio_index_manager_v2.models import IndexManager
from prompt_studio.prompt_studio_index_manager_v2.prompt_studio_index_helper import (
    INDEX_ERROR_MAX_LENGTH,
    ExtractionStatusResult,
    PromptStudioIndexHelper,
)
from prompt_studio.prompt_studio_index_manager_v2.serializers import (
    IndexManagerSerializer,
)


def _pdf(pages: int) -> bytes:
    doc = pdfium.PdfDocument.new()
    for _ in range(pages):
        doc.new_page(612, 792)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class _ToolWithDocument(TestCase):
    def setUp(self) -> None:
        self.addCleanup(UserContext.set_organization_identifier, None)
        slug = f"org-{secrets.token_hex(3)}"
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
            description="",
            organization=self.org,
            created_by=self.user,
        )
        self.tool.grant_owner(self.user)
        adapter = AdapterInstance.objects.create(
            adapter_name=f"adapter-{slug}",
            adapter_id="openai|test",
            adapter_type="LLM",
            adapter_metadata={},
            organization=self.org,
            created_by=self.user,
        )
        self.default = self._profile("default", adapter, is_default=True)
        self.other = self._profile("other", adapter, is_default=False)
        self.document = self._document("a.pdf", size_bytes=2048, page_count=3)

    def _profile(self, name: str, adapter, *, is_default: bool) -> ProfileManager:
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
            prompt_studio_tool=self.tool,
            is_default=is_default,
            created_by=self.user,
        )

    def _document(self, name: str, **fields) -> DocumentManager:
        return DocumentManager.objects.create(
            document_name=name, tool=self.tool, created_by=self.user, **fields
        )

    def _list(self, user: User | None = None) -> list[dict]:
        request = APIRequestFactory().get(
            "/prompt-document/", {"tool_id": str(self.tool.tool_id)}
        )
        force_authenticate(request, user=user or self.user)
        response = PromptStudioDocumentManagerView.as_view({"get": "list"})(
            request, version="v1"
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def _status(self, profile: ProfileManager) -> dict:
        (row,) = self._list()
        return next(
            s
            for s in row["index_status"]
            if s["profile_manager"] == str(profile.profile_id)
        )

    def _index(self, profile: ProfileManager, *, is_summary: bool = False) -> None:
        PromptStudioIndexHelper.handle_index_manager(
            document_id=str(self.document.document_id),
            profile_manager=profile,
            doc_id=f"doc-{secrets.token_hex(3)}",
            is_summary=is_summary,
        )

    def _fail(self, profile: ProfileManager, error: str = "Extractor timed out") -> None:
        PromptStudioIndexHelper.mark_index_failed(
            document_id=str(self.document.document_id),
            profile_manager=profile,
            error=error,
        )


class DocumentStatusTests(_ToolWithDocument):
    def test_existing_fields_are_unchanged(self) -> None:
        (row,) = self._list()
        self.assertEqual(row["document_id"], str(self.document.document_id))
        self.assertEqual(row["document_name"], "a.pdf")
        self.assertEqual(str(row["tool"]), str(self.tool.tool_id))

    def test_base_serializer_is_unchanged(self) -> None:
        # Public shares render this one; the new fields stay off it.
        rep = PromptStudioDocumentManagerSerializer(self.document).data
        self.assertEqual(set(rep), {"document_id", "document_name", "tool"})

    def test_size_and_pages(self) -> None:
        (row,) = self._list()
        self.assertEqual((row["size_bytes"], row["page_count"]), (2048, 3))

    def test_older_documents_have_no_size_or_pages(self) -> None:
        self.document.delete()
        self._document("old.pdf")
        (row,) = self._list()
        self.assertIsNone(row["size_bytes"])
        self.assertIsNone(row["page_count"])

    def test_every_profile_is_listed(self) -> None:
        (row,) = self._list()
        listed = {s["profile_manager"]: s["is_default"] for s in row["index_status"]}
        self.assertEqual(
            listed,
            {str(self.default.profile_id): True, str(self.other.profile_id): False},
        )

    def test_queries_do_not_grow_with_documents(self) -> None:
        with CaptureQueriesContext(connection) as one:
            self._list()
        for n in range(4):
            self._document(f"more-{n}.pdf")
        with CaptureQueriesContext(connection) as five:
            self.assertEqual(len(self._list()), 5)
        self.assertEqual(len(five), len(one))

    def test_not_indexed_is_pending(self) -> None:
        self.assertEqual(
            self._status(self.default),
            {
                "profile_manager": str(self.default.profile_id),
                "is_default": True,
                "status": "pending",
                "failure_reason": None,
            },
        )

    def test_a_row_without_a_raw_index_is_pending(self) -> None:
        # mark_extraction_status creates rows like this.
        IndexManager.objects.create(
            document_manager=self.document, profile_manager=self.default
        )
        self.assertEqual(self._status(self.default)["status"], "pending")

    def test_indexed(self) -> None:
        self._index(self.default)
        self.assertEqual(self._status(self.default)["status"], "indexed")
        self.assertEqual(self._status(self.other)["status"], "pending")

    def test_failure_and_its_reason_survive_a_reload(self) -> None:
        self._fail(self.default)
        status = self._status(self.default)
        self.assertEqual(status["status"], "failed")
        self.assertEqual(status["failure_reason"], "Extractor timed out")

    def test_failure_after_an_earlier_success_is_failed(self) -> None:
        self._index(self.default)
        self._fail(self.default)
        self.assertEqual(self._status(self.default)["status"], "failed")

    def test_success_clears_the_failure(self) -> None:
        self._fail(self.default)
        self._index(self.default)
        status = self._status(self.default)
        self.assertEqual((status["status"], status["failure_reason"]), ("indexed", None))

    def test_summary_index_leaves_the_failure(self) -> None:
        self._fail(self.default)
        self._index(self.default, is_summary=True)
        self.assertEqual(self._status(self.default)["status"], "failed")

    def test_failure_keeps_the_extraction_status(self) -> None:
        PromptStudioIndexHelper.mark_extraction_status(
            document_id=str(self.document.document_id),
            profile_manager=self.default,
            x2text_config_hash="hash",
            enable_highlight=False,
        )
        self._fail(self.default)
        self.assertTrue(
            PromptStudioIndexHelper.check_extraction_status(
                document_id=str(self.document.document_id),
                profile_manager=self.default,
                x2text_config_hash="hash",
                enable_highlight=False,
            )
        )

    def test_a_long_reason_is_cut(self) -> None:
        self._fail(self.default, "x" * (INDEX_ERROR_MAX_LENGTH + 50))
        self.assertEqual(
            len(self._status(self.default)["failure_reason"]), INDEX_ERROR_MAX_LENGTH
        )


class AccessTests(_ToolWithDocument):
    def _reasons(self, user: User | None = None) -> list:
        (row,) = self._list(user)
        return [(s["status"], s["failure_reason"]) for s in row["index_status"]]

    def test_an_org_member_without_access_sees_the_status_not_the_reason(
        self,
    ) -> None:
        stranger = User.objects.create_user(
            username=f"s-{secrets.token_hex(3)}@example.com",
            email=f"s-{secrets.token_hex(3)}@example.com",
            password=secrets.token_urlsafe(),
        )
        self._fail(self.default)
        self.assertIn(("failed", None), self._reasons(stranger))
        self.assertIn(("failed", "Extractor timed out"), self._reasons())

    def test_the_serializer_hides_the_reason_without_the_flag(self) -> None:
        self._fail(self.default)
        data = PromptStudioDocumentStatusSerializer(self.document).data
        reasons = [s["failure_reason"] for s in data["index_status"]]
        self.assertEqual(reasons, [None, None])

    def test_a_malformed_tool_id_hides_the_reason(self) -> None:
        view = PromptStudioDocumentManagerView()
        request = APIRequestFactory().get("/prompt-document/", {"tool_id": "nope"})
        view.request = Request(request)
        view.request.user = self.user
        self.assertFalse(view._can_open_tool())

    def test_the_index_manager_api_omits_the_reason(self) -> None:
        self._fail(self.default)
        row = IndexManager.objects.get(profile_manager=self.default)
        self.assertNotIn("index_error", IndexManagerSerializer(row).data)


class PromptRunIndexFailureTests(_ToolWithDocument):
    def test_a_failed_dynamic_index_is_recorded(self) -> None:
        self.default.chunk_size = 512
        self.default.save()
        dispatcher = MagicMock()
        dispatcher.dispatch.return_value = SimpleNamespace(
            success=False, error="vector db down"
        )
        helper = PromptStudioHelper
        with (
            patch.object(helper, "_get_dispatcher", return_value=dispatcher),
            patch.object(helper, "_get_platform_api_key", return_value="k"),
            patch.object(helper, "_publish_log"),
            patch(
                "prompt_studio.prompt_studio_core_v2.prompt_studio_helper"
                ".DocumentIndexingService"
            ),
            self.assertRaises(IndexingAPIError),
        ):
            helper.dynamic_indexer(
                profile_manager=self.default,
                tool_id=str(self.tool.tool_id),
                file_path="/tmp/a.pdf",
                org_id=self.org.organization_id,
                document_id=str(self.document.document_id),
                user_id=str(self.user.user_id),
                extracted_text="text",
                reindex=True,
                doc_id_key="key",
            )
        status = self._status(self.default)
        self.assertEqual(status["status"], "failed")
        self.assertIn("vector db down", status["failure_reason"])


class UploadWiringTests(_ToolWithDocument):
    def _upload(self, upload, *, converter=None) -> dict:
        request = APIRequestFactory().post(
            "/upload", {"file": [upload]}, format="multipart"
        )
        force_authenticate(request, user=self.user)
        view = core_views.PromptStudioCoreView.as_view({"post": "upload_for_ide"})
        with (
            patch.object(core_views, "PromptStudioFileHelper"),
            patch.object(core_views, "notify_hubspot_event"),
            patch.object(core_views, "get_plugin", return_value=converter),
            patch.object(
                core_views.UserSessionUtils,
                "get_organization_id",
                return_value=self.org.organization_id,
            ),
        ):
            response = view(request, pk=str(self.tool.tool_id))
        self.assertEqual(response.status_code, 200, response.data)
        (doc,) = response.data["data"]
        return DocumentManager.objects.get(pk=doc["document_id"])

    def test_a_pdf_upload_stores_its_size_and_pages(self) -> None:
        data = _pdf(4)
        document = self._upload(
            SimpleUploadedFile("four.pdf", data, content_type="application/pdf")
        )
        self.assertEqual((document.size_bytes, document.page_count), (len(data), 4))

    def test_a_converted_upload_counts_the_converted_pdf(self) -> None:
        converted = _pdf(2)

        class Converter:
            def should_convert_to_pdf(self, file_type: str) -> bool:
                return True

            def process_file(self, uploaded_file, file_name):
                return converted, f"{file_name}.pdf"

        upload = SimpleUploadedFile("notes.txt", b"plain text", content_type="text/plain")
        validated = MagicMock(validated_data={"file": [upload]})
        with patch.object(core_views, "FileUploadIdeSerializer", return_value=validated):
            document = self._upload(upload, converter={"service_class": Converter})
        self.assertEqual((document.size_bytes, document.page_count), (10, 2))


class IndexErrorInternalApiTests(_ToolWithDocument):
    def _post(self, body: dict) -> int:
        request = RequestFactory().post(
            "/internal/index-error/", json.dumps(body), content_type="application/json"
        )
        return internal_views.index_error(request).status_code

    def _body(self, **overrides) -> dict:
        return {
            "document_id": str(self.document.document_id),
            "profile_manager_id": str(self.default.profile_id),
            "error": "Extractor timed out",
            **overrides,
        }

    def test_records_the_failure(self) -> None:
        self.assertEqual(self._post(self._body()), 200)
        self.assertEqual(self._status(self.default)["status"], "failed")

    def test_records_the_posted_reason_on_the_posted_profile(self) -> None:
        body = self._body(profile_manager_id=str(self.other.profile_id), error="OOM")
        self.assertEqual(self._post(body), 200)
        self.assertEqual(self._status(self.other)["failure_reason"], "OOM")
        self.assertEqual(self._status(self.default)["status"], "pending")

    def test_a_write_failure_is_a_500(self) -> None:
        with patch.object(
            PromptStudioIndexHelper,
            "mark_index_failed",
            return_value=ExtractionStatusResult.WRITE_FAILED,
        ):
            self.assertEqual(self._post(self._body()), 500)

    def test_a_malformed_document_id_is_a_404(self) -> None:
        self.assertEqual(self._post(self._body(document_id="not-a-uuid")), 404)

    def test_the_worker_path_routes_here(self) -> None:
        # The worker client posts to v1/prompt-studio/index-error/.
        match = resolve("/internal/v1/prompt-studio/index-error/")
        self.assertIs(match.func, internal_views.index_error)

    def test_missing_field_is_400(self) -> None:
        self.assertEqual(self._post(self._body(error="")), 400)

    def test_missing_document_is_404(self) -> None:
        self.assertEqual(self._post(self._body(document_id=secrets.token_hex(16))), 404)

    def test_missing_profile_is_404(self) -> None:
        self.assertEqual(
            self._post(self._body(profile_manager_id=secrets.token_hex(16))), 404
        )


class UploadPageCountTests(TestCase):
    def test_pdf_stream_is_counted_and_rewound(self) -> None:
        stream = io.BytesIO(_pdf(4))
        stream.seek(10)
        self.assertEqual(PromptStudioHelper.upload_page_count(stream), 4)
        self.assertEqual(stream.tell(), 0)

    def test_converted_bytes_are_counted(self) -> None:
        self.assertEqual(PromptStudioHelper.upload_page_count(_pdf(2)), 2)

    def test_no_pdf_or_unreadable_is_none(self) -> None:
        self.assertIsNone(PromptStudioHelper.upload_page_count(None))
        self.assertIsNone(PromptStudioHelper.upload_page_count(io.BytesIO(b"not a pdf")))
