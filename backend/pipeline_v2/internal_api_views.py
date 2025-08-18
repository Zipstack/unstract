import logging

# serializers.py
# internal_api_views.py
from api_v2.models import APIDeployment
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet
from utils.organization_utils import filter_queryset_by_organization

from pipeline_v2.models import Pipeline

from .serializers.internal import APIDeploymentSerializer, PipelineSerializer

logger = logging.getLogger(__name__)


class PipelineInternalViewSet(ViewSet):
    # def retrieve(self, request, pk=None):
    #     logger.info(f"Retrieving pipeline data for +++++++++++++++++++++++ {pk}")
    #     try:
    #         queryset = Pipeline.objects.filter(id=pk)
    #         logger.info(f"Queryset SQL: {queryset.query}")
    #         queryset = filter_queryset_by_organization(queryset, request, "organization")
    #         logger.info(f"Queryset SQL after organization filter: {queryset.query}")
    #         pipeline = get_object_or_404(queryset)
    #         logger.info(f"Pipeline data: {pipeline}")
    #         return Response({
    #             "status": "success",
    #             "pipeline": PipelineSerializer(pipeline).data
    #         })
    #     except Pipeline.DoesNotExist:
    #         queryset = APIDeployment.objects.filter(id=pk)
    #         logger.info(f"Queryset SQL: {queryset.query}")
    #         queryset = filter_queryset_by_organization(queryset, request, "organization")
    #         logger.info(f"Queryset SQL after organization filter: {queryset.query}")
    #         pipeline = get_object_or_404(queryset)
    #         logger.info(f"Pipeline data: {pipeline}")
    #         return Response({
    #             "status": "success",
    #             "pipeline": APIDeploymentSerializer(pipeline).data
    #         })
    #     except Exception as e:
    #         logger.error(f"Pipeline not found for {pk}: {e}")
    #         return Response({
    #             "status": "error",
    #             "message": "Pipeline not found"
    #         }, status=404)

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
