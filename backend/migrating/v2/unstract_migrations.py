"""Migration utilities for Unstract.

This module provides the UnstractMigration class which extends MigrationQuery.
Additional migrations can be provided through pluggable_apps.migrations_ext
which will be dynamically loaded if available.
"""

import logging

from migrating.v2.query import MigrationQuery

logger = logging.getLogger(__name__)


class UnstractMigration(MigrationQuery):
    """Migration query class that supports extensible migrations.

    Additional migrations can be loaded from pluggable_apps.migrations_ext
    if that module is available.
    """

    def get_public_schema_migrations(self) -> list[dict[str, str]]:
        """Returns a list of dictionaries containing the schema migration details.

        Returns:
            list: A list of dictionaries containing the schema migration details.
        """
        core_migrations = super().get_public_schema_migrations()

        try:
            from pluggable_apps.migrations_ext.migrations import (
                get_extended_public_schema_migrations,
            )
            return core_migrations + get_extended_public_schema_migrations(self.v2_schema)
        except ImportError:
            pass

        return core_migrations

    def get_organization_migrations(
        self, schema: str, organization_id: str
    ) -> list[dict[str, str]]:
        """Returns a list of dictionaries containing the organization migration details.

        Args:
            schema (str): The name of the schema for the organization.
            organization_id (str): The ID of the organization.

        Returns:
            list: A list of dictionaries containing the organization migration details.
        """
        core_migrations = super().get_organization_migrations(schema, organization_id)

        try:
            from pluggable_apps.migrations_ext.migrations import (
                get_extended_organization_migrations,
            )
            return core_migrations + get_extended_organization_migrations(
                self.v2_schema, schema, organization_id
            )
        except ImportError:
            pass

        return core_migrations
