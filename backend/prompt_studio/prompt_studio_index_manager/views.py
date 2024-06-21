from typing import Optional

from django.db.models import QuerySet
from llama_index.core.vector_stores import VectorStoreQuery, VectorStoreQueryResult
from prompt_studio.prompt_profile_manager.profile_manager_helper import (
    ProfileManagerHelper,
)
from prompt_studio.prompt_studio_core.exceptions import DefaultProfileError
from prompt_studio.prompt_studio_core.prompt_ide_base_tool import PromptIdeBaseTool
from prompt_studio.prompt_studio_index_manager.constants import IndexManagerKeys
from prompt_studio.prompt_studio_index_manager.serializers import IndexManagerSerializer
from rest_framework import status, viewsets
from rest_framework.response import Response
from rest_framework.versioning import URLPathVersioning
from unstract.sdk.constants import LogLevel
from unstract.sdk.embedding import Embedding
from unstract.sdk.vector_db import VectorDB
from utils.filtering import FilterHelper
from utils.user_session import UserSessionUtils

from .models import IndexManager


class IndexManagerView(viewsets.ModelViewSet):
    versioning_class = URLPathVersioning
    queryset = IndexManager.objects.all()
    serializer_class = IndexManagerSerializer

    def get_queryset(self) -> Optional[QuerySet]:
        filter_args = FilterHelper.build_filter_args(
            self.request,
            IndexManagerKeys.PROFILE_MANAGER,
            IndexManagerKeys.DOCUMENT_MANAGER,
        )
        queryset = None
        if filter_args:
            queryset = IndexManager.objects.filter(**filter_args)
        return queryset

    def get_indexed_data_for_profile(self, request) -> Response:
        queryset = self.get_queryset()
        org_id = UserSessionUtils.get_organization_id(request)
        util = PromptIdeBaseTool(log_level=LogLevel.INFO, org_id=org_id)
        result = {}

        if queryset is not None:
            # Perform operations on the queryset
            # Example: iterate through queryset and print each object's id
            for obj in queryset:
                profile_manager_id = obj.profile_manager_id
                document_name = str(obj.document_manager.document_name)
                try:
                    profile_manager = ProfileManagerHelper.get_profile_manager(
                        profile_manager_id=profile_manager_id
                    )
                except ValueError as e:
                    raise DefaultProfileError(str(e))
                vector_db_id = str(profile_manager.vector_store.id)
                embedding_model_id = str(profile_manager.embedding_model.id)

                embedding = Embedding(
                    tool=util,
                    adapter_instance_id=embedding_model_id,
                    usage_kwargs={},
                )

                vector_db = VectorDB(
                    tool=util,
                    adapter_instance_id=vector_db_id,
                    embedding=embedding,
                )
                q = VectorStoreQuery(
                    query_embedding=embedding.get_query_embedding(" "),
                    doc_ids=[obj.raw_index_id],
                    similarity_top_k=100,
                )
                n: VectorStoreQueryResult = vector_db.query(query=q)
                all_text = []
                for node in n.nodes:
                    all_text.append(node.get_content())
                result[document_name] = all_text

            response = result
            return Response(response, status=status.HTTP_200_OK)
        else:
            response = "No data found"
            return Response(response, status=status.HTTP_200_OK)
