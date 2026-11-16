from django.urls import path

from agent_kv.views import AgentKVKeyViewSet

urlpatterns = [
    path(
        "keys/",
        AgentKVKeyViewSet.as_view({"get": "list", "post": "create"}),
        name="agent_kv_key_list",
    ),
    path(
        "keys/<uuid:pk>/",
        AgentKVKeyViewSet.as_view(
            {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}
        ),
        name="agent_kv_key_detail",
    ),
    path(
        "keys/<uuid:pk>/rotate/",
        AgentKVKeyViewSet.as_view({"post": "rotate"}),
        name="agent_kv_key_rotate",
    ),
]
