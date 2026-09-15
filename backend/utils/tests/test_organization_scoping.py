"""``filter_queryset_by_organization`` must fail closed.

Every caller reaches it with OrganizationFilterBackend inert, either by opting
out with ``skip_org_filter = True`` or by being on a view class that declares
no filter backends at all, so this helper is their only tenant boundary.
Returning the queryset unfiltered when there is no organization context
therefore returns every organization's rows, and the absent-header case is
reachable: the internal auth middleware warns and continues rather than
rejecting.
"""

import secrets

import pytest
from account_v2.models import Organization
from django.test import TestCase
from utils.organization_utils import filter_queryset_by_organization
from workflow_manager.workflow_v2.models.workflow import Workflow


_ABSENT = object()


class _Request:
    """Stands in for the request object the helper reads context off."""

    def __init__(self, organization_id=_ABSENT, path="/internal/test/"):
        # Two distinct shapes reach production, which reads the attribute with
        # getattr(..., None): the attribute missing entirely, and the attribute
        # present and None. Defaulting to None would collapse them.
        if organization_id is not _ABSENT:
            self.organization_id = organization_id
        self.path = path


@pytest.mark.django_db
class FilterQuerysetByOrganizationTest(TestCase):
    def setUp(self) -> None:
        self.org_a = self._org("a")
        self.org_b = self._org("b")
        self.wf_a = Workflow.objects.create(
            workflow_name=f"wf-a-{secrets.token_hex(3)}", organization=self.org_a
        )
        self.wf_b = Workflow.objects.create(
            workflow_name=f"wf-b-{secrets.token_hex(3)}", organization=self.org_b
        )

    def _org(self, tag: str) -> Organization:
        slug = f"org-{tag}-{secrets.token_hex(3)}"
        return Organization.objects.create(
            name=slug, display_name=slug, organization_id=slug
        )

    def _filter(self, request):
        # _base_manager, not objects: Workflow's default manager is itself
        # org-scoped off UserContext, which would empty the queryset before the
        # helper ever ran and make these tests pass for the wrong reason. The
        # helper's contract is "given a queryset, scope it", so hand it an
        # unscoped one.
        return filter_queryset_by_organization(Workflow._base_manager.all(), request)

    def test_missing_org_context_returns_nothing(self):
        """The header is optional at the middleware, so this is reachable."""
        assert not self._filter(_Request()).exists()

    def test_falsy_org_context_returns_nothing(self):
        for falsy in ("", None):
            with self.subTest(organization_id=falsy):
                assert not self._filter(_Request(organization_id=falsy)).exists()

    def test_unresolvable_org_returns_nothing(self):
        request = _Request(organization_id="does-not-exist")
        assert not self._filter(request).exists()

    def test_valid_org_returns_only_its_own_rows(self):
        rows = self._filter(_Request(organization_id=self.org_a.organization_id))
        assert list(rows) == [self.wf_a]

    def test_other_org_rows_are_never_included(self):
        for org, mine, theirs in (
            (self.org_a, self.wf_a, self.wf_b),
            (self.org_b, self.wf_b, self.wf_a),
        ):
            with self.subTest(org=org.organization_id):
                rows = list(self._filter(_Request(organization_id=org.organization_id)))
                assert mine in rows
                assert theirs not in rows
