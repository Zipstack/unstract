import logging

from api_v2.models import APIDeployment
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from utils.organization_utils import filter_queryset_by_organization

from pipeline_v2.models import Pipeline

from .serializers.internal import APIDeploymentSerializer, PipelineSerializer

logger = logging.getLogger(__name__)


class PipelineInternalViewSet(ViewSet):
    def retrieve(self, request, pk=None):
        logger.info(f"[PipelineInternalViewSet] Retrieving data for ID: {pk}")

        try:
            # 1️⃣ Try in Pipeline
            pipeline_data = self._fetch_single_record(
                pk,
                request,
                Pipeline.objects.filter(id=pk),
                PipelineSerializer,
                "Pipeline",
            )
            if isinstance(pipeline_data, dict):  # Found successfully
                return Response({"status": "success", "pipeline": pipeline_data})
            elif isinstance(pipeline_data, Response):  # Integrity error
                return pipeline_data

            # 2️⃣ Try in APIDeployment
            api_data = self._fetch_single_record(
                pk,
                request,
                APIDeployment.objects.filter(id=pk),
                APIDeploymentSerializer,
                "APIDeployment",
            )
            if isinstance(api_data, dict):
                return Response({"status": "success", "pipeline": api_data})
            elif isinstance(api_data, Response):
                return api_data

            # 3️⃣ Not found anywhere
            logger.warning(f"⚠️ No Pipeline or APIDeployment found for {pk}")
            return Response(
                {"status": "error", "message": "Pipeline not found"}, status=404
            )

        except Exception:
            logger.exception(f"💥 Error retrieving pipeline or deployment for {pk}")
            return Response(
                {"status": "error", "message": "Internal server error"}, status=500
            )

    # Helper function for DRY logic
    def _fetch_single_record(self, pk, request, qs, serializer_cls, model_name):
        qs = filter_queryset_by_organization(qs, request, "organization")
        count = qs.count()

        if count == 1:
            obj = qs.first()
            logger.info(f"✅ Found {model_name} entry: {obj}")
            return serializer_cls(obj).data
        elif count > 1:
            logger.error(f"❌ Multiple {model_name} entries found for {pk}")
            return Response(
                {
                    "status": "error",
                    "message": f"Data integrity error: multiple {model_name} entries found",
                },
                status=500,
            )

        return None  # Not found in this model

    def update(self, request, pk=None):
        """Update pipeline status for scheduler worker."""
        try:
            new_status = request.data.get("status")
            if not new_status:
                return Response(
                    {"status": "error", "message": "Status is required"}, status=400
                )

            # Import here to avoid circular imports
            from pipeline_v2.pipeline_processor import PipelineProcessor

            # Try to update pipeline first
            try:
                pipeline_qs = Pipeline.objects.filter(id=pk)
                pipeline_qs = filter_queryset_by_organization(
                    pipeline_qs, request, "organization"
                )
                pipeline = pipeline_qs.first()

                if pipeline:
                    # Use the PipelineProcessor to update status properly
                    PipelineProcessor.update_pipeline(pk, new_status)

                    return Response(
                        {
                            "status": "success",
                            "pipeline_id": pk,
                            "new_status": new_status,
                            "message": "Pipeline status updated successfully",
                        }
                    )

            except Exception as e:
                logger.error(f"Error updating pipeline status: {e}")
                return Response(
                    {"status": "error", "message": f"Failed to update pipeline: {e}"},
                    status=500,
                )

            # Try API deployment if pipeline not found
            try:
                api_qs = APIDeployment.objects.filter(id=pk)
                api_qs = filter_queryset_by_organization(api_qs, request, "organization")
                api_deployment = api_qs.first()

                if api_deployment:
                    # For API deployments, log the status update
                    logger.info(f"Updated API deployment {pk} status to {new_status}")

                    return Response(
                        {
                            "status": "success",
                            "pipeline_id": pk,
                            "new_status": new_status,
                            "message": "API deployment status updated successfully",
                        }
                    )

            except Exception as e:
                logger.error(f"Error updating API deployment status: {e}")
                return Response(
                    {
                        "status": "error",
                        "message": f"Failed to update API deployment: {e}",
                    },
                    status=500,
                )

            # Not found in either model
            return Response(
                {"status": "error", "message": "Pipeline or API deployment not found"},
                status=404,
            )

        except Exception as e:
            logger.error(f"Error updating pipeline/API deployment status for {pk}: {e}")
            return Response(
                {"status": "error", "message": "Internal server error"}, status=500
            )
