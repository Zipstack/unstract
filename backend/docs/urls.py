from django.urls import path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view

schema_view = get_schema_view(
    openapi.Info(
        title="Unstract APIs",
        default_version="v1",
        description="<Unstract description>",
    ),
    public=False,
)

urlpatterns = [
    path(
        "doc/",
        schema_view.with_ui("redoc", cache_timeout=0),
        name="schema-redoc",
    ),
]
