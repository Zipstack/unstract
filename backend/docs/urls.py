from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

app_name = "docs"

urlpatterns = [
    path(
        "doc/schema/",
        SpectacularAPIView.as_view(),
        name="schema",
    ),
    path(
        "doc/",
        SpectacularRedocView.as_view(url_name="public:docs:schema"),
        name="schema-redoc",
    ),
]
