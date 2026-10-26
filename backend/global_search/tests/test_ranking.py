"""Ranking against the real database: prefix before substring, name before
description, and a deterministic order inside a tier.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from permissions.tests.base import CoOwnerOrgTestMixin

from global_search.tests.base import DESCRIBED_TYPES, OSS_BUILDERS, search


class SearchRankingTests(CoOwnerOrgTestMixin, TestCase):
    def setUp(self) -> None:
        self._seed_org()

    def _results(self, type_key: str, query: str, limit: int = 20) -> list[dict]:
        response = search(self.admin, q=query, types=type_key, limit=limit)
        groups = response.data["groups"]
        return groups[0]["results"] if groups else []

    def test_name_prefix_before_name_substring(self) -> None:
        for type_key, build in OSS_BUILDERS.items():
            with self.subTest(type=type_key):
                # Best tier created first: recency alone would order it last.
                prefix = build(self.org, self.owner, f"kappa-{type_key}")
                inner = build(self.org, self.owner, f"old-kappa-{type_key}")
                results = self._results(type_key, "kappa")
                self.assertEqual(
                    [r["id"] for r in results], [str(prefix.pk), str(inner.pk)]
                )
                self.assertEqual(
                    [r["match"] for r in results], ["name_prefix", "name"]
                )

    def test_name_before_description(self) -> None:
        for type_key in sorted(DESCRIBED_TYPES):
            build = OSS_BUILDERS[type_key]
            with self.subTest(type=type_key):
                # Best tier created first: recency alone would reverse it.
                name_inner = build(self.org, self.owner, f"x-lambda-{type_key}")
                desc_prefix = build(
                    self.org, self.owner, f"d1-{type_key}", "lambda first"
                )
                desc_inner = build(
                    self.org, self.owner, f"d2-{type_key}", "about lambda things"
                )
                results = self._results(type_key, "LAMBDA")
                self.assertEqual(
                    [r["id"] for r in results],
                    [str(name_inner.pk), str(desc_prefix.pk), str(desc_inner.pk)],
                )
                self.assertEqual(
                    [r["match"] for r in results],
                    ["name", "description_prefix", "description"],
                )

    def test_ties_go_to_most_recently_modified(self) -> None:
        build = OSS_BUILDERS["workflow"]
        older = build(self.org, self.owner, "sigma-one")
        newer = build(self.org, self.owner, "sigma-two")
        # bulk paths keep an explicit modified_at, see BaseModelQuerySet.
        type(older).objects.filter(pk=older.pk).update(
            modified_at=timezone.now() - timedelta(days=1)
        )
        results = self._results("workflow", "sigma")
        self.assertEqual([r["id"] for r in results], [str(newer.pk), str(older.pk)])

    def test_has_more_and_limit(self) -> None:
        build = OSS_BUILDERS["connector"]
        for i in range(3):
            build(self.org, self.owner, f"omega-{i}")
        response = search(self.admin, q="omega", types="connector", limit=2)
        (group,) = response.data["groups"]
        self.assertEqual(len(group["results"]), 2)
        self.assertTrue(group["has_more"])

        response = search(self.admin, q="omega", types="connector", limit=3)
        self.assertFalse(response.data["groups"][0]["has_more"])

    def test_wildcards_are_literal(self) -> None:
        build = OSS_BUILDERS["workflow"]
        build(self.org, self.owner, "plain-name")
        # Matches "_100" only if "_" were a single-character wildcard.
        build(self.org, self.owner, "rateX100")
        literal = build(self.org, self.owner, "rate_100%")
        response = search(self.admin, q="_100", types="workflow")
        self.assertEqual(
            [r["id"] for r in response.data["groups"][0]["results"]], [str(literal.pk)]
        )
        self.assertEqual(search(self.admin, q="%%", types="workflow").data["groups"], [])
