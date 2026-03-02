"""
Tests for Enrichment Merger implementation.

This module tests the EnrichmentMerger class including merging logic,
conflict resolution, and metadata tracking.
"""

import uuid

import pytest

from lookup.services.enrichment_merger import EnrichmentMerger


class TestEnrichmentMerger:
    """Test cases for EnrichmentMerger class."""

    @pytest.fixture
    def merger(self):
        """Create an EnrichmentMerger instance."""
        return EnrichmentMerger()

    @pytest.fixture
    def sample_enrichments(self):
        """Create sample enrichments for testing."""
        return [
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Vendor Matcher',
                'data': {
                    'canonical_vendor': 'Slack',
                    'vendor_category': 'SaaS'
                },
                'confidence': 0.95,
                'execution_time_ms': 1234,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Product Classifier',
                'data': {
                    'product_type': 'Software',
                    'license_model': 'Subscription'
                },
                'confidence': 0.88,
                'execution_time_ms': 567,
                'cached': True
            }
        ]

    # ========== No Conflicts Tests ==========

    def test_merge_no_conflicts(self, merger, sample_enrichments):
        """Test merging enrichments with no overlapping fields."""
        result = merger.merge(sample_enrichments)

        # Check merged data has all fields
        assert 'canonical_vendor' in result['data']
        assert 'vendor_category' in result['data']
        assert 'product_type' in result['data']
        assert 'license_model' in result['data']

        # Check values are correct
        assert result['data']['canonical_vendor'] == 'Slack'
        assert result['data']['vendor_category'] == 'SaaS'
        assert result['data']['product_type'] == 'Software'
        assert result['data']['license_model'] == 'Subscription'

        # Check no conflicts were resolved
        assert result['conflicts_resolved'] == 0

        # Check enrichment details
        assert len(result['enrichment_details']) == 2
        assert result['enrichment_details'][0]['lookup_project_name'] == 'Vendor Matcher'
        assert result['enrichment_details'][0]['fields_added'] == ['canonical_vendor', 'vendor_category']
        assert result['enrichment_details'][1]['lookup_project_name'] == 'Product Classifier'
        assert result['enrichment_details'][1]['fields_added'] == ['product_type', 'license_model']

    def test_merge_empty_enrichments(self, merger):
        """Test merging empty list of enrichments."""
        result = merger.merge([])

        assert result['data'] == {}
        assert result['conflicts_resolved'] == 0
        assert result['enrichment_details'] == []

    def test_merge_single_enrichment(self, merger):
        """Test merging with only one enrichment."""
        enrichment = {
            'project_id': uuid.uuid4(),
            'project_name': 'Solo Lookup',
            'data': {'field1': 'value1', 'field2': 'value2'},
            'confidence': 0.9,
            'execution_time_ms': 100,
            'cached': False
        }

        result = merger.merge([enrichment])

        assert result['data'] == {'field1': 'value1', 'field2': 'value2'}
        assert result['conflicts_resolved'] == 0
        assert len(result['enrichment_details']) == 1
        assert result['enrichment_details'][0]['fields_added'] == ['field1', 'field2']

    # ========== Confidence-Based Resolution Tests ==========

    def test_higher_confidence_wins(self, merger):
        """Test that higher confidence value wins in conflict."""
        enrichments = [
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Low Confidence',
                'data': {'category': 'Communication'},
                'confidence': 0.80,
                'execution_time_ms': 100,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'High Confidence',
                'data': {'category': 'Collaboration'},
                'confidence': 0.95,
                'execution_time_ms': 200,
                'cached': False
            }
        ]

        result = merger.merge(enrichments)

        # Higher confidence should win
        assert result['data']['category'] == 'Collaboration'
        assert result['conflicts_resolved'] == 1

        # Check which lookup contributed the field
        details = result['enrichment_details']
        assert details[0]['fields_added'] == []  # Lost the conflict
        assert details[1]['fields_added'] == ['category']  # Won the conflict

    def test_equal_confidence_first_wins(self, merger):
        """Test that first-complete wins when confidence is equal."""
        enrichments = [
            {
                'project_id': uuid.uuid4(),
                'project_name': 'First',
                'data': {'status': 'active'},
                'confidence': 0.90,
                'execution_time_ms': 100,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Second',
                'data': {'status': 'inactive'},
                'confidence': 0.90,  # Same confidence
                'execution_time_ms': 200,
                'cached': False
            }
        ]

        result = merger.merge(enrichments)

        # First should win (first-complete-wins)
        assert result['data']['status'] == 'active'
        assert result['conflicts_resolved'] == 0  # No resolution needed, kept existing

    def test_confidence_beats_no_confidence(self, merger):
        """Test that enrichment with confidence beats one without."""
        enrichments = [
            {
                'project_id': uuid.uuid4(),
                'project_name': 'No Confidence',
                'data': {'vendor': 'Microsoft'},
                'confidence': None,
                'execution_time_ms': 100,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Has Confidence',
                'data': {'vendor': 'Slack'},
                'confidence': 0.75,
                'execution_time_ms': 200,
                'cached': False
            }
        ]

        result = merger.merge(enrichments)

        # Confidence should win
        assert result['data']['vendor'] == 'Slack'
        assert result['conflicts_resolved'] == 1

    def test_no_confidence_first_wins(self, merger):
        """Test first-complete wins when neither has confidence."""
        enrichments = [
            {
                'project_id': uuid.uuid4(),
                'project_name': 'First No Conf',
                'data': {'region': 'US'},
                'confidence': None,
                'execution_time_ms': 100,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Second No Conf',
                'data': {'region': 'EU'},
                'confidence': None,
                'execution_time_ms': 200,
                'cached': False
            }
        ]

        result = merger.merge(enrichments)

        # First should win
        assert result['data']['region'] == 'US'
        assert result['conflicts_resolved'] == 0

    # ========== Multiple Conflicts Tests ==========

    def test_multiple_conflicts_same_enrichments(self, merger):
        """Test resolving multiple field conflicts between same enrichments."""
        enrichments = [
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Enrichment A',
                'data': {
                    'field1': 'A1',
                    'field2': 'A2',
                    'field3': 'A3'
                },
                'confidence': 0.70,
                'execution_time_ms': 100,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Enrichment B',
                'data': {
                    'field1': 'B1',  # Conflict
                    'field2': 'B2',  # Conflict
                    'field4': 'B4'   # No conflict
                },
                'confidence': 0.85,
                'execution_time_ms': 200,
                'cached': True
            }
        ]

        result = merger.merge(enrichments)

        # Higher confidence (B) should win conflicts
        assert result['data']['field1'] == 'B1'
        assert result['data']['field2'] == 'B2'
        assert result['data']['field3'] == 'A3'  # Only from A
        assert result['data']['field4'] == 'B4'  # Only from B

        assert result['conflicts_resolved'] == 2

    def test_three_way_conflicts(self, merger):
        """Test resolving conflicts among three enrichments."""
        enrichments = [
            {
                'project_id': uuid.uuid4(),
                'project_name': 'First',
                'data': {'category': 'Cat1', 'type': 'Type1'},
                'confidence': 0.60,
                'execution_time_ms': 100,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Second',
                'data': {'category': 'Cat2', 'vendor': 'Vendor2'},
                'confidence': 0.80,
                'execution_time_ms': 200,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Third',
                'data': {'category': 'Cat3', 'type': 'Type3'},
                'confidence': 0.75,
                'execution_time_ms': 300,
                'cached': True
            }
        ]

        result = merger.merge(enrichments)

        # Second should win category (0.80 confidence)
        assert result['data']['category'] == 'Cat2'
        # Third should win type (0.75 > 0.60)
        assert result['data']['type'] == 'Type3'
        # Vendor only from Second
        assert result['data']['vendor'] == 'Vendor2'

        assert result['conflicts_resolved'] == 2  # category and type conflicts

    # ========== Metadata Tracking Tests ==========

    def test_enrichment_details_tracking(self, merger):
        """Test that enrichment details are correctly tracked."""
        project_id1 = uuid.uuid4()
        project_id2 = uuid.uuid4()

        enrichments = [
            {
                'project_id': project_id1,
                'project_name': 'Lookup 1',
                'data': {'field1': 'value1'},
                'confidence': 0.9,
                'execution_time_ms': 1500,
                'cached': True
            },
            {
                'project_id': project_id2,
                'project_name': 'Lookup 2',
                'data': {'field2': 'value2'},
                'confidence': 0.85,
                'execution_time_ms': 800,
                'cached': False
            }
        ]

        result = merger.merge(enrichments)

        details = result['enrichment_details']
        assert len(details) == 2

        # Check first enrichment details
        assert details[0]['lookup_project_id'] == str(project_id1)
        assert details[0]['lookup_project_name'] == 'Lookup 1'
        assert details[0]['confidence'] == 0.9
        assert details[0]['cached'] is True
        assert details[0]['execution_time_ms'] == 1500
        assert details[0]['fields_added'] == ['field1']

        # Check second enrichment details
        assert details[1]['lookup_project_id'] == str(project_id2)
        assert details[1]['lookup_project_name'] == 'Lookup 2'
        assert details[1]['confidence'] == 0.85
        assert details[1]['cached'] is False
        assert details[1]['execution_time_ms'] == 800
        assert details[1]['fields_added'] == ['field2']

    def test_fields_added_with_conflicts(self, merger):
        """Test fields_added tracking when conflicts are resolved."""
        enrichments = [
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Winner',
                'data': {'shared': 'win_value', 'unique1': 'value1'},
                'confidence': 0.95,
                'execution_time_ms': 100,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Loser',
                'data': {'shared': 'lose_value', 'unique2': 'value2'},
                'confidence': 0.50,
                'execution_time_ms': 200,
                'cached': False
            }
        ]

        result = merger.merge(enrichments)

        details = result['enrichment_details']
        # Winner should have both its fields
        assert 'shared' in details[0]['fields_added']
        assert 'unique1' in details[0]['fields_added']

        # Loser should only have its unique field
        assert 'shared' not in details[1]['fields_added']
        assert 'unique2' in details[1]['fields_added']

    # ========== Edge Cases Tests ==========

    def test_missing_optional_fields(self, merger):
        """Test handling of enrichments with missing optional fields."""
        enrichments = [
            {
                'project_id': None,  # Missing ID
                'project_name': 'No ID Lookup',
                'data': {'field1': 'value1'},
                # Missing confidence
                # Missing execution_time_ms
                # Missing cached
            },
            {
                # Minimal valid enrichment
                'data': {'field2': 'value2'}
            }
        ]

        result = merger.merge(enrichments)

        assert result['data']['field1'] == 'value1'
        assert result['data']['field2'] == 'value2'
        assert result['conflicts_resolved'] == 0

        # Check defaults are handled
        details = result['enrichment_details']
        assert details[0]['lookup_project_id'] is None
        assert details[0]['confidence'] is None
        assert details[0]['execution_time_ms'] == 0  # Default
        assert details[0]['cached'] is False  # Default

        assert details[1]['lookup_project_name'] == 'Unknown'  # Default

    def test_empty_data_fields(self, merger):
        """Test handling enrichments with empty data."""
        enrichments = [
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Empty Data',
                'data': {},  # Empty
                'confidence': 0.9,
                'execution_time_ms': 100,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Has Data',
                'data': {'field': 'value'},
                'confidence': 0.8,
                'execution_time_ms': 200,
                'cached': False
            }
        ]

        result = merger.merge(enrichments)

        assert result['data'] == {'field': 'value'}
        assert result['conflicts_resolved'] == 0
        assert result['enrichment_details'][0]['fields_added'] == []
        assert result['enrichment_details'][1]['fields_added'] == ['field']

    def test_complex_value_types(self, merger):
        """Test merging with complex value types (lists, dicts)."""
        enrichments = [
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Complex Types',
                'data': {
                    'tags': ['tag1', 'tag2'],
                    'metadata': {'key': 'value'},
                    'count': 42
                },
                'confidence': 0.9,
                'execution_time_ms': 100,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'More Complex',
                'data': {
                    'tags': ['tag3', 'tag4'],  # Conflict - different list
                    'settings': {'option': True}
                },
                'confidence': 0.95,
                'execution_time_ms': 200,
                'cached': False
            }
        ]

        result = merger.merge(enrichments)

        # Higher confidence wins for tags
        assert result['data']['tags'] == ['tag3', 'tag4']
        assert result['data']['metadata'] == {'key': 'value'}
        assert result['data']['count'] == 42
        assert result['data']['settings'] == {'option': True}
        assert result['conflicts_resolved'] == 1

    # ========== Integration Tests ==========

    def test_real_world_scenario(self, merger):
        """Test a realistic scenario with multiple lookups."""
        enrichments = [
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Vendor Standardization',
                'data': {
                    'canonical_vendor': 'Slack Technologies',
                    'vendor_id': 'SLACK-001',
                    'vendor_category': 'Communication'
                },
                'confidence': 0.92,
                'execution_time_ms': 1200,
                'cached': False
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Product Mapping',
                'data': {
                    'product_name': 'Slack Workspace',
                    'product_sku': 'SLK-WS-ENT',
                    'vendor_category': 'Collaboration',  # Conflict
                    'license_type': 'Per User'
                },
                'confidence': 0.88,
                'execution_time_ms': 850,
                'cached': True
            },
            {
                'project_id': uuid.uuid4(),
                'project_name': 'Cost Center Assignment',
                'data': {
                    'cost_center': 'CC-IT-001',
                    'department': 'Information Technology',
                    'budget_category': 'Software'
                },
                'confidence': None,  # No confidence score
                'execution_time_ms': 450,
                'cached': True
            }
        ]

        result = merger.merge(enrichments)

        # Check all fields are present
        expected_fields = [
            'canonical_vendor', 'vendor_id', 'vendor_category',
            'product_name', 'product_sku', 'license_type',
            'cost_center', 'department', 'budget_category'
        ]
        for field in expected_fields:
            assert field in result['data']

        # vendor_category conflict: 0.92 > 0.88, first wins
        assert result['data']['vendor_category'] == 'Communication'

        # Should have 1 conflict resolved
        assert result['conflicts_resolved'] == 1

        # Check enrichment details
        assert len(result['enrichment_details']) == 3
        assert result['enrichment_details'][0]['fields_added'] == [
            'canonical_vendor', 'vendor_id', 'vendor_category'
        ]
        # Product mapping lost vendor_category conflict
        assert 'vendor_category' not in result['enrichment_details'][1]['fields_added']
        assert 'product_name' in result['enrichment_details'][1]['fields_added']
