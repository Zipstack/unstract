"""Regression tests for the two guards on ``DELETE registry/<pk>/``.

The route added in this PR is the first by-PK operation on
``PromptStudioRegistryView``, which previously exposed only ``list``. Two
things gate it, and both are load-bearing:

1. **Authorization** (``IsRegistryToolOwner``). The viewset carries no
   ``permission_classes`` and ``DEFAULT_PERMISSION_CLASSES`` is empty, so
   without this every member of an organization could delete any other
   member's exported tool by PK. ``OrganizationFilterBackend`` runs inside
   ``get_object()`` and blocks *cross-org* access, but not intra-org.

2. **In-use refusal** (409). An exported tool still attached to a workflow must
   not be deletable, or those workflows break.

``has_object_permission`` is pure logic over collaborators, so these tests stub
the Django-coupled boundary (``permissions.permission``,
``OrganizationMemberService``) and exercise the real method body. Django is not
importable in a plain checkout, so the class body is extracted from source --
mirroring ``prompt_studio_core_v2/tests/test_build_index_payload.py``. A rename
fails these tests rather than silently skipping them.

The in-use check is asserted against the same predicate the view applies
(a non-empty set of dependent workflow IDs raises), without standing up the ORM.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]
PERMISSION_MODULE = BACKEND_DIR / "prompt_studio" / "permission.py"

START_MARKER = "class IsRegistryToolOwner(permissions.BasePermission):"


class _User:
    def __init__(self, name: str, is_service_account: bool = False) -> None:
        self.name = name
        self.is_service_account = is_service_account

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User {self.name}>"


class _CustomTool:
    """Stand-in for the parent Prompt Studio project."""

    def __init__(self, owner: _User) -> None:
        self.owner = owner


class _RegistryRow:
    """Stand-in for a ``PromptStudioRegistry`` row.

    ``custom_tool`` is nullable, so it may be ``None`` for legacy rows exported
    before the link existed; those fall back to the row's own owner.
    """

    def __init__(self, custom_tool: _CustomTool | None, owner: _User) -> None:
        self.custom_tool = custom_tool
        self.owner = owner


class _Request:
    def __init__(self, user: _User) -> None:
        self.user = user


def _build_permission(*, org_admins: set[str]) -> Any:
    """Extract the real ``IsRegistryToolOwner`` against stubbed collaborators."""
    source = PERMISSION_MODULE.read_text()
    if START_MARKER not in source:
        pytest.fail(
            f"Could not find {START_MARKER!r} in {PERMISSION_MODULE}. If it was "
            "renamed, update this test rather than deleting it."
        )
    body = textwrap.dedent(source[source.index(START_MARKER) :])

    class _BasePermission:
        pass

    class _Permissions:
        BasePermission = _BasePermission

    def _is_resource_owner(user: _User, obj: Any) -> bool:
        return getattr(obj, "owner", None) is user

    class _OrganizationMemberService:
        @staticmethod
        def is_user_organization_admin(user: _User) -> bool:
            return user.name in org_admins

    namespace: dict[str, Any] = {
        "permissions": _Permissions,
        "_is_resource_owner": _is_resource_owner,
        "OrganizationMemberService": _OrganizationMemberService,
        "Request": object,
        "APIView": object,
        "Any": Any,
    }
    exec(compile(body, str(PERMISSION_MODULE), "exec"), namespace)
    return namespace["IsRegistryToolOwner"]()


OWNER = _User("owner")
STRANGER = _User("stranger")
ADMIN = _User("admin")
SERVICE = _User("service", is_service_account=True)


def _linked_row(owner: _User = OWNER) -> _RegistryRow:
    """A normal row whose parent project is owned by ``owner``."""
    return _RegistryRow(custom_tool=_CustomTool(owner=owner), owner=_User("unused"))


class TestRegistryToolDeleteAuthorization:
    def test_project_owner_may_delete(self) -> None:
        permission = _build_permission(org_admins=set())
        assert (
            permission.has_object_permission(_Request(OWNER), None, _linked_row()) is True
        )

    def test_other_org_member_may_not_delete(self) -> None:
        """The IDOR this guard exists to close.

        Org filtering already blocks cross-org access; this covers a member of
        the *same* org who does not own the project.
        """
        permission = _build_permission(org_admins=set())

        allowed = permission.has_object_permission(
            _Request(STRANGER), None, _linked_row()
        )

        assert allowed is False, (
            "A non-owner in the same organization must not be able to delete "
            "another member's exported tool"
        )

    def test_org_admin_may_delete(self) -> None:
        permission = _build_permission(org_admins={"admin"})
        assert (
            permission.has_object_permission(_Request(ADMIN), None, _linked_row()) is True
        )

    def test_service_account_may_delete(self) -> None:
        permission = _build_permission(org_admins=set())
        assert (
            permission.has_object_permission(_Request(SERVICE), None, _linked_row())
            is True
        )

    def test_ownership_follows_the_parent_project_not_the_row(self) -> None:
        """Ownership is inherited from ``custom_tool``, mirroring IsParentToolOwner.

        The row's own ``owner`` must be ignored while a parent exists, otherwise
        a stale export-time owner could outrank the project's current owner.
        """
        row = _RegistryRow(custom_tool=_CustomTool(owner=OWNER), owner=STRANGER)
        permission = _build_permission(org_admins=set())

        assert permission.has_object_permission(_Request(STRANGER), None, row) is False
        assert permission.has_object_permission(_Request(OWNER), None, row) is True

    def test_unlinked_legacy_row_falls_back_to_its_own_owner(self) -> None:
        """``custom_tool`` is nullable; those rows must stay deletable by their owner."""
        row = _RegistryRow(custom_tool=None, owner=OWNER)
        permission = _build_permission(org_admins=set())

        assert permission.has_object_permission(_Request(OWNER), None, row) is True
        assert permission.has_object_permission(_Request(STRANGER), None, row) is False


VIEWS_MODULE = BACKEND_DIR / "prompt_studio" / "prompt_studio_registry_v2" / "views.py"

GUARD_MARKERS = (
    "    def _get_deployment_types(self, workflow_ids: set) -> set:",
    "    def _refuse_if_in_use(self, instance: PromptStudioRegistry) -> None:",
    "    @staticmethod\n    def _in_use_detail(deployment_types: set) -> str:",
)


class _InUseError(Exception):
    """Stand-in for ``RegistryToolInUseError``, whose 409 is asserted separately."""

    status_code = 409

    def __init__(self, detail: str = "") -> None:
        super().__init__(detail)
        self.detail = detail


def _queryset(rows: list[Any]) -> Any:
    """Minimal chainable stand-in for the ORM calls the guard makes."""

    class _QS:
        def filter(self, **_: Any) -> _QS:
            return self

        def values_list(self, *_: Any, **__: Any) -> _QS:
            return self

        def distinct(self) -> _QS:
            return self

        def exists(self) -> bool:
            return bool(rows)

        def __iter__(self) -> Any:
            return iter(rows)

    return _QS()


def _build_guard(
    *,
    dependent_workflow_ids: list[str],
    api_deployments: bool = False,
    pipeline_types: list[str] | None = None,
    manual_review: bool = False,
) -> Any:
    """Extract the real in-use guard against a stubbed ORM.

    Same technique as ``_build_permission``: the method bodies come from
    ``views.py``, so a change to the query, the raise, or the message wording
    lands here rather than passing against a restated copy.
    """
    source = VIEWS_MODULE.read_text()
    parts = []
    for marker in GUARD_MARKERS:
        if marker not in source:
            pytest.fail(
                f"Could not find {marker!r} in {VIEWS_MODULE}. If the guard was "
                "renamed or inlined, update this test rather than deleting it."
            )
        start = source.index(marker)
        rest = source[start + len(marker) :]
        # Each method runs to the next top-level `    def ` / `    @` sibling.
        end = len(rest)
        for needle in ("\n    def ", "\n    @"):
            found = rest.find(needle)
            if found != -1:
                end = min(end, found)
        parts.append(marker + rest[:end])

    body = "class _Guard:\n" + "\n".join(parts) + "\n"

    class _Model:
        def __init__(self, qs: Any) -> None:
            self.objects = qs

    class _PipelineType:
        ETL = "ETL"
        TASK = "TASK"

    class _Pipeline:
        objects = None
        PipelineType = _PipelineType

    _Pipeline.objects = _queryset(pipeline_types or [])

    class _ConnectionType:
        MANUALREVIEW = "MANUALREVIEW"

    class _WorkflowEndpoint:
        objects = _queryset([1] if manual_review else [])
        ConnectionType = _ConnectionType

    class _DeploymentType:
        API_DEPLOYMENT = "API Deployment"
        ETL_PIPELINE = "ETL Pipeline"
        TASK_PIPELINE = "Task Pipeline"
        HUMAN_QUALITY_REVIEW = "Human in the Loop"

    namespace: dict[str, Any] = {
        "ToolInstance": _Model(_queryset(dependent_workflow_ids)),
        "APIDeployment": _Model(_queryset([1] if api_deployments else [])),
        "Pipeline": _Pipeline,
        "WorkflowEndpoint": _WorkflowEndpoint,
        "DeploymentType": _DeploymentType,
        "RegistryToolInUseError": _InUseError,
        "PromptStudioRegistry": object,
        "logger": _SilentLogger(),
        "Any": Any,
    }
    exec(compile(body, str(VIEWS_MODULE), "exec"), namespace)
    return namespace["_Guard"]()


class _SilentLogger:
    def info(self, *_: Any, **__: Any) -> None:
        pass


class _Instance:
    def __init__(self) -> None:
        self.pk = "tool-1"
        self.prompt_registry_id = "tool-1"


class TestRegistryToolInUseRefusal:
    """The 409 guard, driven through the real method bodies from ``views.py``.

    These exercise ``_refuse_if_in_use`` itself -- the workflow query, the
    raise, and the message construction. The previous version restated the
    predicate as ``bool(ids)``, which passed regardless of what the view did.

    Route binding and permission wiring need a live request cycle (and so a
    database); ``backend/conftest.py`` auto-marks such tests ``integration``,
    which runs in the rig's integration tier rather than this PR's unit tier.
    That boundary is why these stop at the guard.
    """

    def test_tool_used_by_a_workflow_is_refused(self) -> None:
        guard = _build_guard(dependent_workflow_ids=["wf-1"], api_deployments=True)

        with pytest.raises(_InUseError) as excinfo:
            guard._refuse_if_in_use(_Instance())

        assert excinfo.value.status_code == 409, (
            "An in-use tool is a caller-correctable conflict, not a server "
            "fault; the neighbouring ToolDeleteError's 500 is the wrong model"
        )

    def test_unused_tool_is_deletable(self) -> None:
        """No dependants means the guard stands aside -- it is not a blanket ban."""
        guard = _build_guard(dependent_workflow_ids=[])

        assert guard._refuse_if_in_use(_Instance()) is None

    def test_refusal_names_the_blocking_deployment(self) -> None:
        """The 409 must say *where* the tool is used, or the caller cannot act."""
        guard = _build_guard(dependent_workflow_ids=["wf-1"], api_deployments=True)

        with pytest.raises(_InUseError) as excinfo:
            guard._refuse_if_in_use(_Instance())

        assert "API Deployment" in excinfo.value.detail

    def test_refusal_names_every_distinct_blocker(self) -> None:
        guard = _build_guard(
            dependent_workflow_ids=["wf-1", "wf-2"],
            api_deployments=True,
            pipeline_types=["ETL"],
            manual_review=True,
        )

        with pytest.raises(_InUseError) as excinfo:
            guard._refuse_if_in_use(_Instance())

        detail = excinfo.value.detail
        for expected in ("API Deployment", "ETL Pipeline", "Human in the Loop"):
            assert expected in detail

    def test_refusal_falls_back_when_no_deployment_is_identifiable(self) -> None:
        """A workflow need not be deployed anywhere; the refusal still stands."""
        guard = _build_guard(dependent_workflow_ids=["wf-1"])

        with pytest.raises(_InUseError) as excinfo:
            guard._refuse_if_in_use(_Instance())

        assert "one or more workflows" in excinfo.value.detail

    def test_in_use_error_is_a_409(self) -> None:
        """Deleting an in-use tool is a conflict, not a server error.

        The neighbouring ``ToolDeleteError`` is a 500; this must not be modelled
        on it, since the condition is caller-correctable.
        """
        source = (
            BACKEND_DIR / "prompt_studio" / "prompt_studio_registry_v2" / "exceptions.py"
        ).read_text()

        assert "class RegistryToolInUseError" in source, (
            "RegistryToolInUseError is missing; the in-use guard has no way to "
            "signal a conflict"
        )
        body = source[source.index("class RegistryToolInUseError") :]
        assert "status_code = 409" in body.split("class ")[1], (
            "RegistryToolInUseError must be a 409 so callers can distinguish a "
            "correctable conflict from a server fault"
        )
