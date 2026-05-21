"""Regression tests for ``UserFilterRegistry``.

These tests guard the plumbing that identity-scoping plugins use to scope
User / OrganizationMember querysets. A future refactor that breaks the
registry contract (e.g., loses dedupe-on-register, swallows plugin
exceptions, mishandles unregister) would silently let cross-environment
identities leak — the very failure mode the registry exists to prevent.

No Django app registry / DB is required: the registry only depends on
``django.db.models.QuerySet`` as a static type hint, and the tests use
``unittest.mock`` to fake the queryset chain.
"""

from __future__ import annotations

import logging
import unittest
from unittest.mock import MagicMock

from account_v2.user_filter_registry import UserFilterRegistry


class UserFilterRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        # Class-level state — clear before every test to avoid bleed.
        UserFilterRegistry.clear()
        self.addCleanup(UserFilterRegistry.clear)

    def test_apply_with_no_filters_is_identity(self) -> None:
        qs = MagicMock(name="queryset")
        self.assertIs(UserFilterRegistry.apply(qs, "user"), qs)

    def test_register_appends_filter(self) -> None:
        def fn(qs, kind):  # noqa: ANN001 - inline test helper
            return qs

        UserFilterRegistry.register(fn)
        self.assertIn(fn, UserFilterRegistry._filters)

    def test_register_dedupes(self) -> None:
        def fn(qs, kind):  # noqa: ANN001
            return qs

        UserFilterRegistry.register(fn)
        UserFilterRegistry.register(fn)
        self.assertEqual(UserFilterRegistry._filters.count(fn), 1)

    def test_unregister_removes_filter(self) -> None:
        def fn(qs, kind):  # noqa: ANN001
            return qs

        UserFilterRegistry.register(fn)
        UserFilterRegistry.unregister(fn)
        self.assertNotIn(fn, UserFilterRegistry._filters)

    def test_unregister_unknown_is_noop(self) -> None:
        def fn(qs, kind):  # noqa: ANN001
            return qs

        # Must not raise.
        UserFilterRegistry.unregister(fn)

    def test_clear_empties_registry(self) -> None:
        UserFilterRegistry.register(lambda qs, kind: qs)
        UserFilterRegistry.register(lambda qs, kind: qs)
        UserFilterRegistry.clear()
        self.assertEqual(UserFilterRegistry._filters, [])

    def test_apply_runs_filters_in_registration_order(self) -> None:
        order: list[str] = []

        def first(qs, kind):  # noqa: ANN001
            order.append("first")
            return qs

        def second(qs, kind):  # noqa: ANN001
            order.append("second")
            return qs

        UserFilterRegistry.register(first)
        UserFilterRegistry.register(second)
        UserFilterRegistry.apply(MagicMock(), "user")
        self.assertEqual(order, ["first", "second"])

    def test_apply_threads_filtered_queryset_through_chain(self) -> None:
        qs0 = MagicMock(name="qs0")
        qs1 = MagicMock(name="qs1")
        qs2 = MagicMock(name="qs2")

        def fn_a(qs, kind):  # noqa: ANN001
            self.assertIs(qs, qs0)
            return qs1

        def fn_b(qs, kind):  # noqa: ANN001
            self.assertIs(qs, qs1)
            return qs2

        UserFilterRegistry.register(fn_a)
        UserFilterRegistry.register(fn_b)
        self.assertIs(UserFilterRegistry.apply(qs0, "user"), qs2)

    def test_apply_reraises_plugin_exceptions_with_attribution_log(self) -> None:
        # Fail-closed semantics: a broken plugin must not silently let
        # un-scoped users leak into a downstream query. The exception must
        # propagate AND the offending fn must be identifiable in the log.
        def broken(qs, kind):  # noqa: ANN001
            raise RuntimeError("simulated plugin bug")

        UserFilterRegistry.register(broken)
        with self.assertLogs("account_v2.user_filter_registry", level="ERROR") as cm:
            with self.assertRaises(RuntimeError):
                UserFilterRegistry.apply(MagicMock(), "user")
        joined = "\n".join(cm.output)
        self.assertIn("user_filter plugin raised", joined)
        # Plugin attribution: the failing fn's repr should appear in the log
        # so an operator knows which plugin to investigate.
        self.assertIn("broken", joined)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
