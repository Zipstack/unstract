"""Tests for Look-Up system database migrations."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class TestLookupMigrations(TransactionTestCase):
    """Test suite for Look-Up database migrations."""

    @property
    def app(self):
        return "lookup"

    @property
    def migrate_from(self):
        return None  # Initial migration

    @property
    def migrate_to(self):
        return [(self.app, "0001_initial")]

    def setUp(self):
        """Set up test environment."""
        assert (
            self.migrate_from and self.migrate_to
        ), "TestCase '{}' must define migrate_from and migrate_to properties".format(
            type(self).__name__
        )
        self.migrate_from = [(self.app, self.migrate_from)]
        self.migrate_to = [(self.app, self.migrate_to[0][1])]
        executor = MigrationExecutor(connection)
        old_apps = executor.loader.project_state(self.migrate_from).apps

        # Reverse to the original migration
        executor.migrate(self.migrate_from)

        self.apps_before = old_apps

    def test_migration_can_be_applied(self):
        """Test that the migration can be applied successfully."""
        executor = MigrationExecutor(connection)

        # Apply migrations
        executor.migrate(self.migrate_to)

        # Check tables exist
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_name IN (
                    'lookup_projects',
                    'lookup_data_sources',
                    'lookup_prompt_templates',
                    'prompt_studio_lookup_links'
                )
                """
            )
            tables = [row[0] for row in cursor.fetchall()]

        assert len(tables) == 4, f"Expected 4 tables, found {len(tables)}: {tables}"
        assert "lookup_projects" in tables
        assert "lookup_data_sources" in tables
        assert "lookup_prompt_templates" in tables
        assert "prompt_studio_lookup_links" in tables

    def test_migration_can_be_reversed(self):
        """Test that the migration can be reversed successfully."""
        executor = MigrationExecutor(connection)

        # Apply migration
        executor.migrate(self.migrate_to)

        # Reverse migration
        executor.migrate(self.migrate_from)

        # Check tables don't exist
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_name IN (
                    'lookup_projects',
                    'lookup_data_sources',
                    'lookup_prompt_templates',
                    'prompt_studio_lookup_links'
                )
                """
            )
            tables = [row[0] for row in cursor.fetchall()]

        assert (
            len(tables) == 0
        ), f"Tables should not exist after reversal, found: {tables}"

    def test_constraints_are_enforced(self):
        """Test that all database constraints are properly enforced."""
        from django.contrib.auth import get_user_model
        from account.models import Organization
        from lookup.models import LookupProject, LookupDataSource

        User = get_user_model()

        # Create test user and organization
        org = Organization.objects.create(name="Test Org")
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="password"
        )

        # Test CHECK constraint on lookup_type
        with pytest.raises(Exception):
            LookupProject.objects.create(
                name="Invalid Type Project",
                lookup_type="invalid_type",
                llm_provider="openai",
                llm_model="gpt-4",
                organization=org,
                created_by=user,
            )

        # Test CHECK constraint on extraction_status
        project = LookupProject.objects.create(
            name="Valid Project",
            lookup_type="static_data",
            llm_provider="openai",
            llm_model="gpt-4",
            organization=org,
            created_by=user,
        )

        with pytest.raises(Exception):
            LookupDataSource.objects.create(
                project=project,
                file_name="test.pdf",
                file_path="/path/to/file.pdf",
                file_size=1024,
                file_type="pdf",
                extraction_status="invalid_status",
                uploaded_by=user,
            )

    def test_version_trigger_functionality(self):
        """Test that the version management trigger works correctly."""
        from django.contrib.auth import get_user_model
        from account.models import Organization
        from lookup.models import LookupProject, LookupDataSource

        User = get_user_model()

        # Create test data
        org = Organization.objects.create(name="Test Org")
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="password"
        )

        project = LookupProject.objects.create(
            name="Version Test Project",
            lookup_type="static_data",
            llm_provider="openai",
            llm_model="gpt-4",
            organization=org,
            created_by=user,
        )

        # Create first data source
        ds1 = LookupDataSource.objects.create(
            project=project,
            file_name="v1.pdf",
            file_path="/path/v1.pdf",
            file_size=1024,
            file_type="pdf",
            uploaded_by=user,
        )

        # Verify first version
        ds1.refresh_from_db()
        assert ds1.version_number == 1
        assert ds1.is_latest is True

        # Create second data source
        ds2 = LookupDataSource.objects.create(
            project=project,
            file_name="v2.pdf",
            file_path="/path/v2.pdf",
            file_size=2048,
            file_type="pdf",
            uploaded_by=user,
        )

        # Verify second version
        ds2.refresh_from_db()
        assert ds2.version_number == 2
        assert ds2.is_latest is True

        # Verify first version is no longer latest
        ds1.refresh_from_db()
        assert ds1.is_latest is False

    def test_indexes_are_created(self):
        """Test that all required indexes are created."""
        with connection.cursor() as cursor:
            # Check for index existence on lookup_projects
            cursor.execute(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'lookup_projects'
                AND indexname IN (
                    'idx_lookup_proj_org',
                    'idx_lookup_proj_created_by',
                    'idx_lookup_proj_updated'
                )
                """
            )
            project_indexes = [row[0] for row in cursor.fetchall()]

        assert len(project_indexes) == 3

        with connection.cursor() as cursor:
            # Check for index existence on lookup_data_sources
            cursor.execute(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'lookup_data_sources'
                AND indexname IN (
                    'idx_lookup_ds_project',
                    'idx_lookup_ds_latest',
                    'idx_lookup_ds_created',
                    'idx_lookup_ds_status'
                )
                """
            )
            ds_indexes = [row[0] for row in cursor.fetchall()]

        assert len(ds_indexes) == 4

    def test_foreign_key_constraints(self):
        """Test that foreign key relationships work correctly."""
        from django.contrib.auth import get_user_model
        from account.models import Organization
        from lookup.models import (
            LookupProject,
            LookupDataSource,
            LookupPromptTemplate,
        )

        User = get_user_model()

        # Create test data
        org = Organization.objects.create(name="Test Org")
        user = User.objects.create_user(
            username="testuser", email="test@example.com", password="password"
        )

        project = LookupProject.objects.create(
            name="FK Test Project",
            lookup_type="static_data",
            llm_provider="openai",
            llm_model="gpt-4",
            organization=org,
            created_by=user,
        )

        # Test cascade delete
        data_source = LookupDataSource.objects.create(
            project=project,
            file_name="test.pdf",
            file_path="/path/test.pdf",
            file_size=1024,
            file_type="pdf",
            uploaded_by=user,
        )

        template = LookupPromptTemplate.objects.create(
            project=project,
            template_text="Test: {{input_data}}",
        )

        # Delete project should cascade
        project_id = project.id
        project.delete()

        # Verify cascaded deletes
        assert not LookupDataSource.objects.filter(id=data_source.id).exists()
        assert not LookupPromptTemplate.objects.filter(id=template.id).exists()
