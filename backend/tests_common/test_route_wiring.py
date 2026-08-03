"""Pin that the guarded routes this PR adds are actually *wired*.

The behavioural suites for these two features drive method bodies extracted
from source (``tests_common.source_extraction``), which asserts what a function
does but not that anything reaches it. That leaves a blind spot the guards
themselves cannot cover: code present in the file but unreachable in production
is indistinguishable from code that is dispatched. Deleting the registry DELETE
route, or unwiring ``IsRegistryToolOwner`` from ``destroy``, both left those
suites fully green while reopening the exact holes they exist to close.

These tests close that spot from the other side -- they assert the *binding*
and nothing about behaviour:

* the URLconf maps the expected HTTP verb to the expected action, and
* the viewset resolves the expected permission class for the destructive action.

They import the real modules rather than extracting source, so a deleted or
renamed import in either view module fails here at collection time. No database
is touched: URL resolution and ``get_permissions()`` are pure, so these stay in
the per-PR unit tier rather than being auto-marked ``integration`` by
``backend/conftest.py``.
"""

from __future__ import annotations

import ast
import builtins
import inspect
import sys
import textwrap

from api_v2.api_key_views import APIKeyViewSet
from django.urls import resolve, reverse
from permissions.permission import IsParentDeploymentOwner
from prompt_studio.permission import IsRegistryToolOwner
from prompt_studio.prompt_studio_registry_v2.views import PromptStudioRegistryView

REGISTRY_URLCONF = "prompt_studio.prompt_studio_registry_v2.urls"
API_URLCONF = "api_v2.urls"

_SAMPLE_UUID = "00000000-0000-0000-0000-000000000001"


def _actions(name: str, urlconf: str, **kwargs: str) -> dict[str, str]:
    """Verb -> action map the URLconf binds for ``name``."""
    url = reverse(name, kwargs=kwargs, urlconf=urlconf)
    return resolve(url, urlconf=urlconf).func.actions


class TestRegistryDeleteRouteIsWired:
    """``DELETE registry/<pk>/`` -- the route and its authorization gate."""

    def test_delete_verb_is_bound_to_destroy(self) -> None:
        """Removing the route entirely left the guard suite green."""
        assert _actions(
            "prompt_studio_registry_detail", REGISTRY_URLCONF, pk=_SAMPLE_UUID
        ) == {"delete": "destroy"}

    def test_destroy_resolves_the_owner_permission(self) -> None:
        """Unwiring the gate left ``destroy`` open to any org member."""
        view = PromptStudioRegistryView()
        view.action = "destroy"

        assert any(
            isinstance(perm, IsRegistryToolOwner) for perm in view.get_permissions()
        )

    def test_list_is_not_gated_by_the_owner_permission(self) -> None:
        """Read visibility is derived by ``list_tools``; only deletes narrow.

        Asserts the *resolution* path ran, not merely that the owner class is
        absent: an empty permission list would satisfy the negative on its own
        and prove nothing.
        """
        view = PromptStudioRegistryView()
        view.action = "list"

        permissions = view.get_permissions()

        assert permissions == super(PromptStudioRegistryView, view).get_permissions()
        assert not any(isinstance(perm, IsRegistryToolOwner) for perm in permissions)


class TestApiKeyRoutesAreWired:
    """``keys/{api,pipeline}/...`` -- the routes whose ``create`` closes an IDOR."""

    def test_api_path_route_binds_post_to_create(self) -> None:
        """``create`` moved out of the viewset left the create suite green."""
        assert _actions("api_key_api", API_URLCONF, api_id="api-1")["post"] == "create"

    def test_pipeline_path_route_binds_post_to_create(self) -> None:
        assert (
            _actions("api_key_pipeline", API_URLCONF, pipeline_id="pipeline-1")["post"]
            == "create"
        )

    def test_body_only_routes_bind_post_to_create(self) -> None:
        """The body-only routes reach the same guarded ``create``."""
        assert _actions("api_keys_api", API_URLCONF)["post"] == "create"
        assert _actions("api_keys_pipeline", API_URLCONF)["post"] == "create"

    def test_create_is_overridden_on_the_viewset(self) -> None:
        """``create`` must be *this* viewset's, not ``ModelViewSet``'s default.

        ``callable(APIKeyViewSet.create)`` is not enough: the inherited
        ``CreateModelMixin.create`` satisfies it, so moving the override to a
        dead class -- reopening the IDOR it closes -- would still pass. Assert
        the override is defined in the class body itself.
        """
        assert "create" in vars(APIKeyViewSet)

    def test_every_global_create_uses_resolves(self) -> None:
        """A deleted or renamed import 500s ``create`` at request time only.

        ``create`` reaches ``status``/``Response``/``serializers`` on its
        success path, so a missing import raises ``NameError`` per request
        rather than at import time -- invisible to a test that merely imports
        the module. Resolve each global the body loads instead.
        """
        module = sys.modules[APIKeyViewSet.__module__]
        # Parse the override itself rather than walking the module for any
        # ``create``: a second definition anywhere in the file would otherwise
        # break this with an unpack error naming nothing about the defect.
        source = textwrap.dedent(inspect.getsource(vars(APIKeyViewSet)["create"]))
        (func,) = ast.parse(source).body
        loaded = {
            node.id
            for node in ast.walk(func)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        local = {"self", "request", "args", "kwargs"} | {
            node.id
            for node in ast.walk(func)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store)
        }

        unresolved = [
            name
            for name in sorted(loaded - local)
            if not hasattr(module, name) and not hasattr(builtins, name)
        ]
        assert not unresolved, f"create() references unimported names: {unresolved}"

    def test_create_object_checks_its_target(self) -> None:
        """The IDOR fix is ``create`` calling ``check_object_permissions``.

        ``create`` is collection-level, so DRF never calls ``get_object()`` and
        ``has_object_permission`` never runs on its own. The override must make
        that call itself, or any org member can mint a key for a deployment
        they do not own.
        """
        source = inspect.getsource(vars(APIKeyViewSet)["create"])

        assert "check_object_permissions" in source

    def test_create_resolves_the_parent_deployment_permission(self) -> None:
        """``create`` object-checks the target; the class must be resolved for it."""
        view = APIKeyViewSet()
        view.action = "create"

        assert any(
            isinstance(perm, IsParentDeploymentOwner) for perm in view.get_permissions()
        )
