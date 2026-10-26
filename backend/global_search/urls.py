from django.urls import path

from global_search.views import GlobalSearchView

urlpatterns = [
    path("search/", GlobalSearchView.as_view(), name="global_search"),
]
