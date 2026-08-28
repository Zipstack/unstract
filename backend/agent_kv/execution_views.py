from rest_framework.response import Response
from rest_framework.views import APIView

from agent_kv.key_validator import AgentKVKeyValidator


class SubmitView(APIView):
    authentication_classes: list = []
    permission_classes: list = []

    @AgentKVKeyValidator.validate_api_key
    def post(self, request, *args, agent_kv_key=None, **kwargs):
        return Response({"detail": "not implemented"}, status=501)
