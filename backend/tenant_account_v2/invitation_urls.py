from django.urls import path

from tenant_account_v2.invitation_views import InvitationViewSet

invitation_list = InvitationViewSet.as_view(
    {
        "get": InvitationViewSet.list_invitations.__name__,
    }
)

invitation_details = InvitationViewSet.as_view(
    {
        "delete": InvitationViewSet.delete_invitation.__name__,
    }
)


urlpatterns = [
    path("", invitation_list, name="invitation_list"),
    path("<str:id>/", invitation_details, name="invitation_details"),
]
