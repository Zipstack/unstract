from rest_framework.routers import DefaultRouter

from tenant_account_v2.group_views import OrganizationGroupViewSet

router = DefaultRouter(trailing_slash=True)
router.register(r"groups", OrganizationGroupViewSet, basename="organization-group")

urlpatterns = router.urls
