import re

from django.conf import settings
from django.utils.deprecation import MiddlewareMixin


class OrganizationMiddleware(MiddlewareMixin):
    def process_request(self, request):
        tenant_prefix = settings.TENANT_SUBFOLDER_PREFIX.rstrip("/") + "/"
        pattern = rf"^{tenant_prefix}(?P<org_id>[^/]+)/"

        # Check if the URL matches the pattern with organization ID
        match = re.match(pattern, request.path)
        if match:
            # Check if the request path matches any of the whitelisted paths
            if any(
                re.match(path, request.path)
                for path in settings.ORGANIZATION_MIDDLEWARE_WHITELISTED_PATHS
            ):
                request.path_info = "/" + request.path_info
                return

            org_id = match.group("org_id")
            request.organization_id = org_id
            new_path = re.sub(pattern, "/" + tenant_prefix, request.path_info)
            request.path_info = new_path
        else:
            request.organization_id = None
