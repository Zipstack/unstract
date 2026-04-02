"""
Tests for Reference Data Loader implementation.

This module tests the ReferenceDataLoader class including loading latest/specific
versions, concatenation, and extraction validation.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock

import pytest
from django.contrib.auth import get_user_model

from lookup.exceptions import ExtractionNotCompleteError
from lookup.models import LookupDataSource, LookupProject
from lookup.services.reference_data_loader import ReferenceDataLoader

User = get_user_model()


@pytest.mark.django_db
class TestReferenceDataLoader:
    """Test cases for ReferenceDataLoader class."""

    @pytest.fixture
    def mock_storage(self):
        """Create a mock storage client."""
        storage = MagicMock()
        storage.get = Mock(return_value="Default content")
        return storage

    @pytest.fixture
    def loader(self, mock_storage):
        """Create a ReferenceDataLoader instance with mock storage."""
        return ReferenceDataLoader(mock_storage)

    @pytest.fixture
    def test_user(self):
        """Create a test user."""
        return User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    @pytest.fixture
    def test_project(self, test_user):
        """Create a test Look-Up project."""
        return LookupProject.objects.create(
            name="Test Project",
            description="Test project for loader",
            lookup_type='static_data',
            llm_provider='openai',
            llm_model='gpt-4',
            llm_config={'temperature': 0.7},
            organization_id=uuid.uuid4(),
            created_by=test_user
        )

    @pytest.fixture
    def data_sources_completed(self, test_project, test_user):
        """Create 3 completed data sources for testing."""
        sources = []
        for i in range(3):
            source = LookupDataSource.objects.create(
                project=test_project,
                file_name=f"file{i+1}.csv",
                file_path=f"uploads/file{i+1}.csv",
                file_size=1000 * (i + 1),
                file_type="text/csv",
                extracted_content_path=f"extracted/file{i+1}.txt",
                extraction_status='completed',
                version_number=1,
                is_latest=True,
                uploaded_by=test_user
            )
            sources.append(source)
        return sources

    # ========== Load Latest Tests ==========

    def test_load_latest_success(self, loader, mock_storage, test_project,
                                 data_sources_completed):
        """Test successful loading of latest reference data."""
        # Setup mock storage responses
        def storage_get(path):
            if 'file1' in path:
                return "Content from file 1"
            elif 'file2' in path:
                return "Content from file 2"
            elif 'file3' in path:
                return "Content from file 3"
            return "Unknown file"

        mock_storage.get.side_effect = storage_get

        # Load latest data
        result = loader.load_latest_for_project(test_project.id)

        # Verify result structure
        assert 'version' in result
        assert 'content' in result
        assert 'files' in result
        assert 'total_size' in result

        # Check version
        assert result['version'] == 1

        # Check concatenated content
        expected_content = (
            "=== File: file1.csv ===\n\n"
            "Content from file 1\n\n"
            "=== File: file2.csv ===\n\n"
            "Content from file 2\n\n"
            "=== File: file3.csv ===\n\n"
            "Content from file 3"
        )
        assert result['content'] == expected_content

        # Check files metadata
        assert len(result['files']) == 3
        assert result['files'][0]['name'] == 'file1.csv'
        assert result['files'][1]['name'] == 'file2.csv'
        assert result['files'][2]['name'] == 'file3.csv'

        # Check total size
        assert result['total_size'] == 6000  # 1000 + 2000 + 3000

        # Verify storage was called for each file
        assert mock_storage.get.call_count == 3

    def test_load_latest_incomplete_extraction(self, loader, test_project,
                                              test_user):
        """Test loading fails when extraction is incomplete."""
        # Create sources with mixed status
        LookupDataSource.objects.create(
            project=test_project,
            file_name="completed.csv",
            file_path="uploads/completed.csv",
            file_size=1000,
            file_type="text/csv",
            extraction_status='completed',
            version_number=1,
            is_latest=True,
            uploaded_by=test_user
        )

        LookupDataSource.objects.create(
            project=test_project,
            file_name="pending.csv",
            file_path="uploads/pending.csv",
            file_size=2000,
            file_type="text/csv",
            extraction_status='pending',
            version_number=1,
            is_latest=True,
            uploaded_by=test_user
        )

        LookupDataSource.objects.create(
            project=test_project,
            file_name="failed.csv",
            file_path="uploads/failed.csv",
            file_size=3000,
            file_type="text/csv",
            extraction_status='failed',
            extraction_error='Parse error',
            version_number=1,
            is_latest=True,
            uploaded_by=test_user
        )

        # Attempt to load should raise exception
        with pytest.raises(ExtractionNotCompleteError) as exc_info:
            loader.load_latest_for_project(test_project.id)

        # Check error message includes failed files
        assert 'pending.csv' in str(exc_info.value)
        assert 'failed.csv' in str(exc_info.value)
        assert exc_info.value.failed_files == ['pending.csv', 'failed.csv']

    def test_load_latest_no_data_sources(self, loader):
        """Test loading when no data sources exist."""
        non_existent_id = uuid.uuid4()

        with pytest.raises(LookupDataSource.DoesNotExist) as exc_info:
            loader.load_latest_for_project(non_existent_id)

        assert str(non_existent_id) in str(exc_info.value)

    def test_load_latest_order_by_upload(self, loader, mock_storage, test_project,
                                        test_user):
        """Test that files are concatenated in upload order."""
        # Create sources with specific creation times
        source1 = LookupDataSource.objects.create(
            project=test_project,
            file_name="third.csv",  # Named third but uploaded first
            file_path="uploads/third.csv",
            file_size=1000,
            file_type="text/csv",
            extracted_content_path="extracted/third.txt",
            extraction_status='completed',
            version_number=1,
            is_latest=True,
            uploaded_by=test_user
        )
        source1.created_at = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
        source1.save()

        source2 = LookupDataSource.objects.create(
            project=test_project,
            file_name="first.csv",  # Named first but uploaded second
            file_path="uploads/first.csv",
            file_size=2000,
            file_type="text/csv",
            extracted_content_path="extracted/first.txt",
            extraction_status='completed',
            version_number=1,
            is_latest=True,
            uploaded_by=test_user
        )
        source2.created_at = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)
        source2.save()

        def storage_get(path):
            if 'third' in path:
                return "Third content"
            elif 'first' in path:
                return "First content"
            return "Unknown"

        mock_storage.get.side_effect = storage_get

        result = loader.load_latest_for_project(test_project.id)

        # Verify order is by upload time, not name
        assert "=== File: third.csv ===" in result['content']
        assert "=== File: first.csv ===" in result['content']
        assert result['content'].index('third.csv') < result['content'].index('first.csv')

    # ========== Load Specific Version Tests ==========

    def test_load_specific_version(self, loader, mock_storage, test_project,
                                  test_user):
        """Test loading a specific version of reference data."""
        # Create multiple versions
        # Version 1
        LookupDataSource.objects.create(
            project=test_project,
            file_name="v1_file.csv",
            file_path="uploads/v1_file.csv",
            file_size=1000,
            file_type="text/csv",
            extracted_content_path="extracted/v1_file.txt",
            extraction_status='completed',
            version_number=1,
            is_latest=False,
            uploaded_by=test_user
        )

        # Version 2
        LookupDataSource.objects.create(
            project=test_project,
            file_name="v2_file.csv",
            file_path="uploads/v2_file.csv",
            file_size=2000,
            file_type="text/csv",
            extracted_content_path="extracted/v2_file.txt",
            extraction_status='completed',
            version_number=2,
            is_latest=False,
            uploaded_by=test_user
        )

        # Version 3 (latest)
        LookupDataSource.objects.create(
            project=test_project,
            file_name="v3_file.csv",
            file_path="uploads/v3_file.csv",
            file_size=3000,
            file_type="text/csv",
            extracted_content_path="extracted/v3_file.txt",
            extraction_status='completed',
            version_number=3,
            is_latest=True,
            uploaded_by=test_user
        )

        def storage_get(path):
            if 'v1' in path:
                return "Version 1 content"
            elif 'v2' in path:
                return "Version 2 content"
            elif 'v3' in path:
                return "Version 3 content"
            return "Unknown"

        mock_storage.get.side_effect = storage_get

        # Load version 2
        result = loader.load_specific_version(test_project.id, 2)

        assert result['version'] == 2
        assert "Version 2 content" in result['content']
        assert "v2_file.csv" in result['content']
        assert result['files'][0]['name'] == 'v2_file.csv'

        # Load version 1
        result = loader.load_specific_version(test_project.id, 1)

        assert result['version'] == 1
        assert "Version 1 content" in result['content']
        assert "v1_file.csv" in result['content']

    def test_load_specific_version_not_found(self, loader, test_project):
        """Test loading non-existent version."""
        with pytest.raises(LookupDataSource.DoesNotExist) as exc_info:
            loader.load_specific_version(test_project.id, 999)

        assert "Version 999 not found" in str(exc_info.value)

    # ========== Concatenation Tests ==========

    def test_concatenate_sources(self, loader, mock_storage, data_sources_completed):
        """Test concatenation of multiple sources."""
        def storage_get(path):
            if 'file1' in path:
                return "Alpha content"
            elif 'file2' in path:
                return "Beta content"
            elif 'file3' in path:
                return "Gamma content"
            return "Unknown"

        mock_storage.get.side_effect = storage_get

        result = loader.concatenate_sources(data_sources_completed)

        # Check all files are included with headers
        assert "=== File: file1.csv ===" in result
        assert "=== File: file2.csv ===" in result
        assert "=== File: file3.csv ===" in result

        # Check all content is included
        assert "Alpha content" in result
        assert "Beta content" in result
        assert "Gamma content" in result

        # Check double newline separators
        assert "\n\n" in result

    def test_concatenate_with_missing_path(self, loader, test_project, test_user):
        """Test concatenation when extracted_content_path is missing."""
        source = LookupDataSource.objects.create(
            project=test_project,
            file_name="no_path.csv",
            file_path="uploads/no_path.csv",
            file_size=1000,
            file_type="text/csv",
            extracted_content_path=None,  # No extracted path
            extraction_status='completed',  # But marked as completed
            version_number=1,
            is_latest=True,
            uploaded_by=test_user
        )

        result = loader.concatenate_sources([source])

        assert "=== File: no_path.csv ===" in result
        assert "[No extracted content path]" in result

    def test_concatenate_with_storage_error(self, loader, mock_storage,
                                           data_sources_completed):
        """Test concatenation handles storage errors gracefully."""
        mock_storage.get.side_effect = Exception("Storage unavailable")

        result = loader.concatenate_sources(data_sources_completed)

        # Should include error messages instead of content
        assert "[Error loading file: Storage unavailable]" in result
        # But should still have file headers
        assert "=== File: file1.csv ===" in result

    # ========== Validation Tests ==========

    def test_validate_extraction_complete_all_success(self, loader,
                                                     data_sources_completed):
        """Test validation when all extractions are complete."""
        is_complete, failed_files = loader.validate_extraction_complete(
            data_sources_completed
        )

        assert is_complete is True
        assert failed_files == []

    def test_validate_extraction_with_failures(self, loader, test_project, test_user):
        """Test validation identifies incomplete extractions."""
        sources = []

        # Completed
        sources.append(LookupDataSource.objects.create(
            project=test_project,
            file_name="good.csv",
            file_path="uploads/good.csv",
            file_size=1000,
            file_type="text/csv",
            extraction_status='completed',
            version_number=1,
            is_latest=True,
            uploaded_by=test_user
        ))

        # Pending
        sources.append(LookupDataSource.objects.create(
            project=test_project,
            file_name="pending.csv",
            file_path="uploads/pending.csv",
            file_size=2000,
            file_type="text/csv",
            extraction_status='pending',
            version_number=1,
            is_latest=True,
            uploaded_by=test_user
        ))

        # Processing
        sources.append(LookupDataSource.objects.create(
            project=test_project,
            file_name="processing.csv",
            file_path="uploads/processing.csv",
            file_size=3000,
            file_type="text/csv",
            extraction_status='processing',
            version_number=1,
            is_latest=True,
            uploaded_by=test_user
        ))

        # Failed
        sources.append(LookupDataSource.objects.create(
            project=test_project,
            file_name="failed.csv",
            file_path="uploads/failed.csv",
            file_size=4000,
            file_type="text/csv",
            extraction_status='failed',
            version_number=1,
            is_latest=True,
            uploaded_by=test_user
        ))

        is_complete, failed_files = loader.validate_extraction_complete(sources)

        assert is_complete is False
        assert len(failed_files) == 3
        assert 'pending.csv' in failed_files
        assert 'processing.csv' in failed_files
        assert 'failed.csv' in failed_files
        assert 'good.csv' not in failed_files

    # ========== Integration Tests ==========

    def test_end_to_end_multi_file_loading(self, loader, mock_storage, test_project,
                                          test_user):
        """Test complete workflow with multiple files and versions."""
        # Create version 1 with 2 files
        v1_file1 = LookupDataSource.objects.create(
            project=test_project,
            file_name="vendors_v1.csv",
            file_path="uploads/vendors_v1.csv",
            file_size=5000,
            file_type="text/csv",
            extracted_content_path="extracted/vendors_v1.txt",
            extraction_status='completed',
            version_number=1,
            is_latest=False,
            uploaded_by=test_user
        )

        v1_file2 = LookupDataSource.objects.create(
            project=test_project,
            file_name="products_v1.csv",
            file_path="uploads/products_v1.csv",
            file_size=3000,
            file_type="text/csv",
            extracted_content_path="extracted/products_v1.txt",
            extraction_status='completed',
            version_number=1,
            is_latest=False,
            uploaded_by=test_user
        )

        # Create version 2 with 3 files (latest)
        v2_file1 = LookupDataSource.objects.create(
            project=test_project,
            file_name="vendors_v2.csv",
            file_path="uploads/vendors_v2.csv",
            file_size=6000,
            file_type="text/csv",
            extracted_content_path="extracted/vendors_v2.txt",
            extraction_status='completed',
            version_number=2,
            is_latest=True,
            uploaded_by=test_user
        )

        v2_file2 = LookupDataSource.objects.create(
            project=test_project,
            file_name="products_v2.csv",
            file_path="uploads/products_v2.csv",
            file_size=4000,
            file_type="text/csv",
            extracted_content_path="extracted/products_v2.txt",
            extraction_status='completed',
            version_number=2,
            is_latest=True,
            uploaded_by=test_user
        )

        v2_file3 = LookupDataSource.objects.create(
            project=test_project,
            file_name="categories.csv",
            file_path="uploads/categories.csv",
            file_size=2000,
            file_type="text/csv",
            extracted_content_path="extracted/categories.txt",
            extraction_status='completed',
            version_number=2,
            is_latest=True,
            uploaded_by=test_user
        )

        def storage_get(path):
            content_map = {
                'vendors_v1': "Slack\nMicrosoft",
                'products_v1': "Slack Workspace\nTeams",
                'vendors_v2': "Slack\nMicrosoft\nGoogle",
                'products_v2': "Slack Workspace\nTeams\nGoogle Workspace",
                'categories': "Communication\nProductivity"
            }
            for key, value in content_map.items():
                if key in path:
                    return value
            return "Unknown content"

        mock_storage.get.side_effect = storage_get

        # Load latest (v2)
        latest_result = loader.load_latest_for_project(test_project.id)

        assert latest_result['version'] == 2
        assert len(latest_result['files']) == 3
        assert latest_result['total_size'] == 12000  # 6000 + 4000 + 2000
        assert "Google" in latest_result['content']
        assert "categories.csv" in latest_result['content']

        # Load specific version (v1)
        v1_result = loader.load_specific_version(test_project.id, 1)

        assert v1_result['version'] == 1
        assert len(v1_result['files']) == 2
        assert v1_result['total_size'] == 8000  # 5000 + 3000
        assert "Google" not in v1_result['content']  # v1 doesn't have Google
        assert "categories" not in v1_result['content']  # v1 doesn't have categories
