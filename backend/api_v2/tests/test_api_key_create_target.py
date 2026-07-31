"""Guards on ``APIKeyViewSet.create`` for the path-derived target.

``POST keys/api/<api_id>/`` and ``POST keys/pipeline/<pipeline_id>/`` name the
target in the URL. Deriving it there removed the need to repeat it in the body,
but ``create`` is a *collection*-level action: DRF resolves
``IsParentDeploymentOwner`` for it and then never calls ``get_object()``, so
``has_object_permission`` never ran. Any authenticated org member could mint a
live key for a deployment they do not own. The view now performs the object
check itself.

Three things are pinned here, all cheap to break:

1. **Every route authorizes.** The check must cover the body-only routes
   (``keys/api/``, ``keys/pipeline/``) as well as the path ones -- guarding
   only the path form leaves the identical hole reachable by moving the
   identifier into the body.

2. **``IsParentDeploymentOwner`` accepts the parent itself.** The view hands it
   an ``APIDeployment``/``Pipeline``, neither of which declares an ``api`` or
   ``pipeline`` field. A plain ``obj.api`` raises ``AttributeError`` -> 500 on
   every key creation; the lookups must be shape-guarded. An object matching
   neither shape is denied, not admitted.

3. **The path target is authoritative.** A body naming the *other* target is a
   contradiction and must be refused, not silently resolved to whichever wins.

These are unit tests over the real method bodies -- Django settings are not
configured in the unit tier, so collaborators are stubbed and the source is
extracted, mirroring
``prompt_studio_registry_v2/tests/test_registry_tool_delete_guards.py``.
``create`` is *executed* rather than grepped: an earlier version asserted on
source text and so passed against an inverted ``isinstance`` guard and against
the wrong object being handed to ``check_object_permissions``.

The end-to-end request cycle still needs a database and lives in the
integration tier; what runs here is the method body, not the routing.
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
    ``obj.api`` a 500. ``memberships`` is how the permission class recognises
    a parent; both real models get it from ``HasMembersMixin``.
    """

    def __init__(self, owner: _User) -> None:
        self.owner = owner
        self.memberships = ()


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

    class _SilentLogger:
        def warning(self, *_: Any, **__: Any) -> None:
            pass

    namespace: dict[str, Any] = {
        "permissions": _Permissions,
        "_is_resource_owner": _is_resource_owner,
        "_is_service_account": _is_service_account,
        "_is_organization_admin": _is_organization_admin,
        "logger": _SilentLogger(),
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

    def test_an_unrecognised_object_is_denied(self) -> None:
        """An authz gate that cannot identify its subject must fail closed.

        A permissive fallthrough would admit any object that happens to expose
        a matching owner, turning a wrong-type programming error into a silent
        grant instead of a loud failure.
        """

        class _Unexpected:
            def __init__(self, owner: _User) -> None:
                self.owner = owner

        permission = _build_permission(org_admins=set())

        assert (
            permission.has_object_permission(
                _Request(OWNER), None, _Unexpected(owner=OWNER)
            )
            is False
        )


VIEW_MODULE = BACKEND_DIR / "api_v2" / "api_key_views.py"

CREATE_MARKER = (
    "    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:"
)

CREATED = object()
"""Sentinel proving the key was actually minted."""


class _ValidationError(Exception):
    """Stand-in for ``serializers.ValidationError`` (a 400)."""


class _NotFound(Exception):
    """Stand-in for ``APINotFound`` / ``PipelineNotFound`` (a 404)."""


class _PermissionDenied(Exception):
    """Raised by the stub ``check_object_permissions`` (a 403)."""


class _Target:
    """A resolvable APIDeployment/Pipeline row."""

    def __init__(self, target_id: str, owner: _User) -> None:
        self.id = target_id
        self.owner = owner


def _build_create(
    *,
    apis: dict[str, _Target] | None = None,
    pipelines: dict[str, _Target] | None = None,
    requester: _User = OWNER,
) -> Any:
    """Extract and execute the real ``create`` body against stubs.

    Source extraction is used for the same reason as ``_build_permission``:
    Django settings are unconfigured in the unit tier, so the module cannot be
    imported. Executing the real body is what makes these behavioural -- the
    previous version asserted on source *text*, and so passed against an
    inverted ``isinstance`` guard and against the wrong object being handed to
    ``check_object_permissions``.
    """
    source = VIEW_MODULE.read_text()
    if CREATE_MARKER not in source:
        pytest.fail(
            f"Could not find {CREATE_MARKER!r} in {VIEW_MODULE}. If the "
            "signature changed, update this test rather than deleting it."
        )
    start = source.index(CREATE_MARKER)
    rest = source[start + len(CREATE_MARKER) :]
    end = len(rest)
    for needle in ("\n    def ", "\n    @"):
        found = rest.find(needle)
        if found != -1:
            end = min(end, found)
    body = textwrap.dedent(CREATE_MARKER + rest[:end])

    checked: list[Any] = []

    class _Serializers:
        ValidationError = _ValidationError

    class _DeploymentHelper:
        @staticmethod
        def get_api_by_id(api_id: str) -> _Target | None:
            return (apis or {}).get(api_id)

    class _PipelineProcessor:
        @staticmethod
        def get_pipeline_by_id(pipeline_id: str) -> _Target | None:
            return (pipelines or {}).get(pipeline_id)

    class _View:
        """Minimal DRF-ish host for the extracted method."""

        def check_object_permissions(self, request: Any, obj: Any) -> None:
            checked.append(obj)
            # Mirrors IsParentDeploymentOwner: only the owner passes.
            if getattr(obj, "owner", None) is not request.user:
                raise _PermissionDenied()

        def get_serializer(self, data: Any) -> Any:
            return _Serializer(data)

        def perform_create(self, serializer: Any) -> None:
            serializer.saved = True

        def get_success_headers(self, data: Any) -> dict[str, str]:
            return {}

    class _Serializer:
        def __init__(self, data: Any) -> None:
            self.data = data
            self.saved = False

        def is_valid(self, raise_exception: bool = False) -> bool:
            api = self.data.get("api")
            pipeline = self.data.get("pipeline")
            if api and pipeline:
                raise _ValidationError("only one of api/pipeline")
            if not api and not pipeline:
                raise _ValidationError("at least one of api/pipeline")
            return True

    class _Response:
        def __init__(self, data: Any, status: Any = None, headers: Any = None) -> None:
            self.data = data
            self.status = status

    class _Status:
        HTTP_201_CREATED = 201

    namespace: dict[str, Any] = {
        "serializers": _Serializers,
        "DeploymentHelper": _DeploymentHelper,
        "PipelineProcessor": _PipelineProcessor,
        "APINotFound": _NotFound,
        "PipelineNotFound": _NotFound,
        "Response": _Response,
        "status": _Status,
        "Request": object,
        "Any": Any,
    }
    exec(compile(body, str(VIEW_MODULE), "exec"), namespace)

    view = _View()
    view.create = namespace["create"].__get__(view, _View)
    view.checked = checked
    view.requester = requester
    return view


class _Req:
    def __init__(self, data: Any, user: _User) -> None:
        self.data = data
        self.user = user


class TestCreateAuthorizesEveryRoute:
    """The IDOR fix, exercised rather than grepped.

    The hole is reachable from four routes -- api/pipeline, each by path and
    by body. Every one must resolve the target and object-check it.
    """

    def test_path_route_admits_the_owner(self) -> None:
        target = _Target("api-1", OWNER)
        view = _build_create(apis={"api-1": target})

        response = view.create(_Req({}, OWNER), api_id="api-1")

        assert response.status == 201
        assert view.checked == [target], "the target must be object-checked"

    def test_path_route_refuses_a_non_owner(self) -> None:
        view = _build_create(apis={"api-1": _Target("api-1", OWNER)})

        with pytest.raises(_PermissionDenied):
            view.create(_Req({}, STRANGER), api_id="api-1")

    def test_body_only_route_refuses_a_non_owner(self) -> None:
        """The route the path-only fix left open.

        Moving the identifier from the path into the body must not bypass the
        ownership check -- otherwise the IDOR is simply relocated.
        """
        view = _build_create(apis={"api-1": _Target("api-1", OWNER)})

        with pytest.raises(_PermissionDenied):
            view.create(_Req({"api": "api-1"}, STRANGER))

    def test_body_only_route_admits_the_owner(self) -> None:
        target = _Target("api-1", OWNER)
        view = _build_create(apis={"api-1": target})

        response = view.create(_Req({"api": "api-1"}, OWNER))

        assert response.status == 201
        assert view.checked == [target]

    def test_body_only_pipeline_route_refuses_a_non_owner(self) -> None:
        view = _build_create(pipelines={"pipe-1": _Target("pipe-1", OWNER)})

        with pytest.raises(_PermissionDenied):
            view.create(_Req({"pipeline": "pipe-1"}, STRANGER))

    def test_pipeline_path_route_checks_the_pipeline_not_the_api(self) -> None:
        """Guards against the wrong object reaching the permission check."""
        target = _Target("pipe-1", OWNER)
        view = _build_create(pipelines={"pipe-1": target})

        view.create(_Req({}, OWNER), pipeline_id="pipe-1")

        assert view.checked == [target]

    def test_unknown_target_is_a_404(self) -> None:
        view = _build_create(apis={})

        with pytest.raises(_NotFound):
            view.create(_Req({}, OWNER), api_id="missing")


class TestCreateBodyContract:
    def test_non_mapping_body_is_a_400(self) -> None:
        """A JSON array body must 400, not ``AttributeError`` into a 500."""
        view = _build_create(apis={"api-1": _Target("api-1", OWNER)})

        with pytest.raises(_ValidationError):
            view.create(_Req([{"api": "api-1"}], OWNER), api_id="api-1")

    def test_body_naming_the_other_target_is_refused(self) -> None:
        view = _build_create(
            apis={"api-1": _Target("api-1", OWNER)},
            pipelines={"pipe-1": _Target("pipe-1", OWNER)},
        )

        with pytest.raises(_ValidationError):
            view.create(_Req({"pipeline": "pipe-1"}, OWNER), api_id="api-1")

    def test_pipeline_path_with_api_body_is_refused(self) -> None:
        view = _build_create(
            apis={"api-1": _Target("api-1", OWNER)},
            pipelines={"pipe-1": _Target("pipe-1", OWNER)},
        )

        with pytest.raises(_ValidationError):
            view.create(_Req({"api": "api-1"}, OWNER), pipeline_id="pipe-1")

    def test_empty_string_body_value_does_not_defeat_the_path(self) -> None:
        """``setdefault`` used to let ``{"api": ""}`` through as a present key."""
        target = _Target("api-1", OWNER)
        view = _build_create(apis={"api-1": target})

        response = view.create(_Req({"api": ""}, OWNER), api_id="api-1")

        assert response.status == 201
        assert view.checked == [target]

    def test_no_target_anywhere_is_a_400(self) -> None:
        view = _build_create()

        with pytest.raises(_ValidationError):
            view.create(_Req({}, OWNER))
