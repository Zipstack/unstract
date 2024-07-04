import logging
import uuid
from typing import Any

from account.models import Organization
from celery import current_task, shared_task
from django_tenants.utils import get_tenant_model, tenant_context
from pluggable_apps.apps.app_deployment.models import AppDeployment, IndexedDocuments
from pluggable_apps.apps.app_deployment.multi_doc_service import MultiDocService
from pluggable_apps.apps.app_deployment.serializers import FileUploadResponseSerializer
from workflow_manager.endpoint.source import SourceConnector
from workflow_manager.workflow.models import Workflow

logger = logging.getLogger(__name__)


class AppDeploymentHelper:

    @staticmethod
    @shared_task(
        name="file_upload_app_deployment",
        acks_late=True,
        autoretry_for=(Exception,),
        max_retries=1,
        retry_backoff=True,
        retry_backoff_max=500,
        retry_jitter=True,
    )
    def file_upload_app_deployment(
        workflow_id: uuid,
        app_name: str,
        email: str,
        org_id: str,
        **kwargs: dict[str, Any],
    ) -> None:
        """Asynchronous Execution By celery."""
        task_id = current_task.request.id
        logger.info("Task id %s", task_id)

        tenant: Organization = (
            get_tenant_model().objects.filter(schema_name=org_id).first()
        )
        with tenant_context(tenant):

            workflow: Workflow = Workflow.objects.get(pk=workflow_id)
            app: AppDeployment = AppDeployment.objects.get(app_name=app_name)
            source = SourceConnector(workflow=workflow, execution_id="")
            multi_doc_service = MultiDocService(org_id=org_id, email=email)

            file_paths: list[str] = source.list_files_from_source()
            for file_path in file_paths:
                file_name, file_content = source.load_file(file_path)

                response = multi_doc_service.upload_file(
                    file_name=file_name,
                    file_content=file_content,
                    email=email,
                    tag=app_name,
                )

                serializer = FileUploadResponseSerializer(data=response)
                if serializer.is_valid():
                    validated_data = serializer.validated_data
                    for doc in validated_data["doc_ids"]:
                        IndexedDocuments.objects.create(
                            file_name=doc["file_name"],
                            document_id=doc["doc_id"],
                            app_deployment=app,
                        )
