"""Guards on ``APIKeyViewSet.create`` for the path-derived target.

``POST keys/api/<api_id>/`` and ``POST keys/pipeline/<pipeline_id>/`` name the
target in the URL. Deriving it there removed the need to repeat it in the body,
but ``create`` is a *collection*-level action: DRF resolves
``IsParentDeploymentOwner`` for it and then never calls ``get_object()``, so
``has_object_permission`` never ran. Any authenticated org member could mint a
live key for a deployment they do not own. The view now performs the object
check itself.

Two things are pinned here, both cheap to break:

1. **``IsParentDeploymentOwner`` accepts the parent itself.** The view hands it
   an ``APIDeployment``/``Pipeline``, neither of which declares an ``api`` or
   ``pipeline`` field. A plain ``obj.api`` raises ``AttributeError`` -> 500 on
   every key creation; the lookups must be ``getattr`` guarded.

2. **The path target is authoritative.** A body naming the *other* target is a
   contradiction and must be refused, not silently resolved to whichever wins.

These are unit tests over the real method bodies -- Django settings are not
configured in the unit tier, so collaborators are stubbed and the source is
extracted, mirroring
``prompt_studio_registry_v2/tests/test_registry_tool_delete_guards.py``. The
end-to-end request cycle needs a database and lives in the integration tier.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]
PERMISSION_MODULE = BACKEND_DIR / "permissions" / "permission.py"

START_MARKER = "class IsParentDeploymentOwner(permissions.BasePermission):"
END_MARKER = "\nclass "


class _User:
    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.name}>"


class _Request:
    def __init__(self, user: _User) -> None:
        self.user = user


class _APIDeployment:
    """A deployment as the permission class actually receives it.

    Deliberately declares neither ``api`` nor ``pipeline`` -- that is what the
    real model looks like (``APIKey.api`` points *at* it with
    ``related_name="api_keys"``), and it is the shape that made a bare
    ``obj.api`` a 500.
    """

    def __init__(self, owner: _User) -> None:
        self.owner = owner


class _APIKey:
    """A key row, whose ownership is inherited from its parent."""

    def __init__(self, api: Any = None, pipeline: Any = None, owner: Any = None) -> None:
        self.api = api
        self.pipeline = pipeline
        self.owner = owner


def _build_permission(*, org_admins: set[str]) -> Any:
    """Extract the real ``IsParentDeploymentOwner`` against stubbed collaborators."""
    source = PERMISSION_MODULE.read_text()
    if START_MARKER not in source:
        pytest.fail(
            f"Could not find {START_MARKER!r} in {PERMISSION_MODULE}. If it was "
            "renamed, update this test rather than deleting it."
        )
    rest = source[source.index(START_MARKER) :]
    next_class = rest.find(END_MARKER, len(START_MARKER))
    body = textwrap.dedent(rest if next_class == -1 else rest[:next_class])

    class _BasePermission:
        pass

    class _Permissions:
        BasePermission = _BasePermission

    def _is_resource_owner(user: _User, obj: Any) -> bool:
        return getattr(obj, "owner", None) is user

    def _is_service_account(request: _Request) -> bool:
        return getattr(request.user, "is_service_account", False)

    def _is_organization_admin(request: _Request) -> bool:
        return request.user.name in org_admins

    namespace: dict[str, Any] = {
        "permissions": _Permissions,
        "_is_resource_owner": _is_resource_owner,
        "_is_service_account": _is_service_account,
        "_is_organization_admin": _is_organization_admin,
        "Request": object,
        "APIView": object,
        "Any": Any,
    }
    exec(compile(body, str(PERMISSION_MODULE), "exec"), namespace)
    return namespace["IsParentDeploymentOwner"]()


OWNER = _User("owner")
STRANGER = _User("stranger")
ADMIN = _User("admin")


class TestParentDeploymentOwnerAcceptsTheParent:
    """``create`` passes the parent directly; that must not 500 or over-admit."""

    def test_deployment_owner_is_admitted(self) -> None:
        permission = _build_permission(org_admins=set())
        deployment = _APIDeployment(owner=OWNER)

        assert permission.has_object_permission(_Request(OWNER), None, deployment) is True

    def test_non_owner_is_refused(self) -> None:
        """The IDOR this check closes: same-org, not the deployment's owner."""
        permission = _build_permission(org_admins=set())
        deployment = _APIDeployment(owner=OWNER)

        allowed = permission.has_object_permission(_Request(STRANGER), None, deployment)

        assert allowed is False, (
            "A member who does not own the deployment must not be able to mint "
            "an API key for it"
        )

    def test_org_admin_is_admitted(self) -> None:
        permission = _build_permission(org_admins={"admin"})
        deployment = _APIDeployment(owner=OWNER)

        assert permission.has_object_permission(_Request(ADMIN), None, deployment) is True

    def test_a_parent_without_api_or_pipeline_fields_does_not_raise(self) -> None:
        """The regression that a bare ``obj.api`` would reintroduce.

        ``APIDeployment``/``Pipeline`` declare no ``api`` or ``pipeline``
        field, so an unguarded attribute access is an ``AttributeError`` --
        surfacing as a 500 on every single key creation, which is worse than
        the hole it was meant to close.
        """
        permission = _build_permission(org_admins=set())
        deployment = _APIDeployment(owner=OWNER)

        assert not hasattr(deployment, "api")
        assert not hasattr(deployment, "pipeline")
        # Must return a verdict rather than raising.
        assert (
            permission.has_object_permission(_Request(STRANGER), None, deployment)
            is False
        )

    def test_key_rows_still_resolve_through_their_parent(self) -> None:
        """The pre-existing detail-route behaviour must be unchanged."""
        permission = _build_permission(org_admins=set())
        key = _APIKey(api=_APIDeployment(owner=OWNER), owner=STRANGER)

        assert permission.has_object_permission(_Request(OWNER), None, key) is True
        assert permission.has_object_permission(_Request(STRANGER), None, key) is False

    def test_parentless_key_falls_back_to_its_own_owner(self) -> None:
        permission = _build_permission(org_admins=set())
        key = _APIKey(api=None, pipeline=None, owner=OWNER)

        assert permission.has_object_permission(_Request(OWNER), None, key) is True
        assert permission.has_object_permission(_Request(STRANGER), None, key) is False


VIEW_MODULE = BACKEND_DIR / "api_v2" / "api_key_views.py"


class TestCreateContract:
    """The wiring in ``create`` that no unit-level stub can stand in for."""

    def test_create_checks_object_permissions_on_the_path_target(self) -> None:
        """Without this call the permission class is dead code for ``create``."""
        source = VIEW_MODULE.read_text()
        body = source[source.index("    def create(") : source.index("@action")]

        assert body.count("self.check_object_permissions(request,") == 2, (
            "Both the api and pipeline branches must object-check their target; "
            "`create` is collection-level, so DRF never does it for us"
        )

    def test_create_refuses_a_body_naming_the_other_target(self) -> None:
        source = VIEW_MODULE.read_text()
        body = source[source.index("    def create(") : source.index("@action")]

        assert 'request_data.get("pipeline")' in body
        assert 'request_data.get("api")' in body, (
            "A body naming the other target must be refused; silently picking "
            "one would create a key against a resource the URL does not name"
        )

    def test_create_rejects_a_non_mapping_body(self) -> None:
        """A JSON array body must 400, not ``AttributeError`` into a 500."""
        source = VIEW_MODULE.read_text()
        body = source[source.index("    def create(") : source.index("@action")]

        assert "isinstance(request.data, dict)" in body

    def test_path_target_is_assigned_not_defaulted(self) -> None:
        """``setdefault`` let ``{"api": ""}`` through as a present-but-empty key.

        The path names the target, so it is assigned outright; the body cannot
        blank it out into a confusing 400.
        """
        source = VIEW_MODULE.read_text()
        body = source[source.index("    def create(") : source.index("@action")]

        assert 'request_data["api"] = api_id' in body
        assert 'request_data["pipeline"] = pipeline_id' in body
        assert "setdefault" not in body
