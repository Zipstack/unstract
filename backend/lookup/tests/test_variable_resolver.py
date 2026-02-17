"""Tests for the VariableResolver class."""

import json
import pytest
from lookup.services.variable_resolver import VariableResolver


class TestVariableResolver:
    """Test suite for VariableResolver."""

    @pytest.fixture
    def sample_input_data(self):
        """Sample input data for testing."""
        return {
            "vendor_name": "Slack India Pvt Ltd",
            "contract_value": 50000,
            "contract_date": "2024-01-15",
            "line_items": [
                {"product": "Slack Pro", "quantity": 100, "price": 500}
            ],
            "metadata": {
                "region": "APAC",
                "currency": "INR"
            },
            "none_field": None
        }

    @pytest.fixture
    def sample_reference_data(self):
        """Sample reference data for testing."""
        return """Canonical Vendors:
- Slack (variations: Slack Inc, Slack India, Slack Singapore)
- Microsoft (variations: Microsoft Corp, MSFT)
- Google (variations: Google LLC, Google India)"""

    @pytest.fixture
    def resolver(self, sample_input_data, sample_reference_data):
        """Create a VariableResolver instance for testing."""
        return VariableResolver(sample_input_data, sample_reference_data)

    # ==========================================================================
    # Basic Resolution Tests
    # ==========================================================================

    def test_simple_variable_replacement(self, resolver):
        """Test simple variable replacement."""
        template = "Vendor: {{input_data.vendor_name}}"
        result = resolver.resolve(template)
        assert result == "Vendor: Slack India Pvt Ltd"

    def test_reference_data_replacement(self, resolver):
        """Test reference data replacement."""
        template = "Database: {{reference_data}}"
        result = resolver.resolve(template)
        assert "Canonical Vendors" in result
        assert "Slack" in result

    def test_multiple_variables(self, resolver):
        """Test multiple variable replacements in one template."""
        template = "Match {{input_data.vendor_name}} from {{reference_data}}"
        result = resolver.resolve(template)
        assert "Slack India Pvt Ltd" in result
        assert "Canonical Vendors" in result

    # ==========================================================================
    # Dot Notation Tests
    # ==========================================================================

    def test_one_level_dot_notation(self, resolver):
        """Test one level dot notation."""
        template = "Value: {{input_data.contract_value}}"
        result = resolver.resolve(template)
        assert result == "Value: 50000"

    def test_two_level_dot_notation(self, resolver):
        """Test two level dot notation."""
        template = "Region: {{input_data.metadata.region}}"
        result = resolver.resolve(template)
        assert result == "Region: APAC"

    def test_array_indexing(self, resolver):
        """Test array indexing with dot notation."""
        template = "Product: {{input_data.line_items.0.product}}"
        result = resolver.resolve(template)
        assert result == "Product: Slack Pro"

    def test_deep_nesting(self, resolver):
        """Test deep nested path resolution."""
        template = "Price: {{input_data.line_items.0.price}}"
        result = resolver.resolve(template)
        assert result == "Price: 500"

    # ==========================================================================
    # Complex Object Serialization Tests
    # ==========================================================================

    def test_dict_serialization(self, resolver):
        """Test that dicts are serialized to JSON."""
        template = "Metadata: {{input_data.metadata}}"
        result = resolver.resolve(template)
        # Parse the JSON portion to verify it's valid
        json_str = result.replace("Metadata: ", "")
        parsed = json.loads(json_str)
        assert parsed["region"] == "APAC"
        assert parsed["currency"] == "INR"

    def test_list_serialization(self, resolver):
        """Test that lists are serialized to JSON."""
        template = "Items: {{input_data.line_items}}"
        result = resolver.resolve(template)
        # Parse the JSON portion to verify it's valid
        json_str = result.replace("Items: ", "")
        parsed = json.loads(json_str)
        assert len(parsed) == 1
        assert parsed[0]["product"] == "Slack Pro"

    def test_full_input_serialization(self, resolver):
        """Test serializing the entire input_data object."""
        template = "Full data: {{input_data}}"
        result = resolver.resolve(template)
        # Should contain JSON representation
        assert '"vendor_name"' in result
        assert '"contract_value"' in result

    # ==========================================================================
    # Missing Value Tests
    # ==========================================================================

    def test_missing_root_variable(self, resolver):
        """Test missing root variable returns empty string."""
        template = "Missing: {{missing_data}}"
        result = resolver.resolve(template)
        assert result == "Missing: "

    def test_missing_nested_field(self, resolver):
        """Test missing nested field returns empty string."""
        template = "Missing: {{input_data.missing.field}}"
        result = resolver.resolve(template)
        assert result == "Missing: "

    def test_partial_path_missing(self, resolver):
        """Test partially missing path returns empty string."""
        template = "Missing: {{input_data.metadata.missing}}"
        result = resolver.resolve(template)
        assert result == "Missing: "

    def test_none_value(self, resolver):
        """Test that None values are converted to empty string."""
        template = "None field: {{input_data.none_field}}"
        result = resolver.resolve(template)
        assert result == "None field: "

    def test_out_of_bounds_array_index(self, resolver):
        """Test out of bounds array index returns empty string."""
        template = "Missing: {{input_data.line_items.999.product}}"
        result = resolver.resolve(template)
        assert result == "Missing: "

    # ==========================================================================
    # Edge Cases Tests
    # ==========================================================================

    def test_empty_template(self, resolver):
        """Test empty template returns empty string."""
        assert resolver.resolve("") == ""

    def test_no_variables(self, resolver):
        """Test template without variables returns unchanged."""
        template = "Plain text without variables"
        assert resolver.resolve(template) == template

    def test_malformed_variable(self, resolver):
        """Test malformed variable syntax is left unchanged."""
        template = "Malformed: {{unclosed"
        result = resolver.resolve(template)
        assert result == "Malformed: {{unclosed"

    def test_whitespace_in_variable(self, resolver):
        """Test variables with whitespace are handled correctly."""
        template = "Vendor: {{ input_data.vendor_name }}"
        result = resolver.resolve(template)
        assert result == "Vendor: Slack India Pvt Ltd"

    def test_empty_braces(self, resolver):
        """Test empty braces are handled."""
        template = "Empty: {{}}"
        result = resolver.resolve(template)
        assert result == "Empty: "

    # ==========================================================================
    # Variable Detection Tests
    # ==========================================================================

    def test_detect_single_variable(self, resolver):
        """Test detecting a single variable."""
        template = "{{input_data.vendor_name}}"
        variables = resolver.detect_variables(template)
        assert variables == ["input_data.vendor_name"]

    def test_detect_multiple_variables(self, resolver):
        """Test detecting multiple variables."""
        template = "{{input_data.vendor_name}} and {{reference_data}}"
        variables = resolver.detect_variables(template)
        assert set(variables) == {"input_data.vendor_name", "reference_data"}

    def test_detect_duplicate_variables(self, resolver):
        """Test that duplicate variables are deduplicated."""
        template = "{{var}} and {{var}} and {{var}}"
        variables = resolver.detect_variables(template)
        assert variables == ["var"]

    def test_detect_no_variables(self, resolver):
        """Test detecting no variables in plain text."""
        template = "Plain text without variables"
        variables = resolver.detect_variables(template)
        assert variables == []

    def test_detect_variables_with_whitespace(self, resolver):
        """Test detecting variables with whitespace."""
        template = "{{ input_data.vendor }} and {{reference_data}}"
        variables = resolver.detect_variables(template)
        assert set(variables) == {"input_data.vendor", "reference_data"}

    # ==========================================================================
    # Variable Validation Tests
    # ==========================================================================

    def test_validate_existing_variables(self, resolver):
        """Test validation of existing variables."""
        template = "{{input_data.vendor_name}} and {{reference_data}}"
        validation = resolver.validate_variables(template)
        assert validation["input_data.vendor_name"] is True
        assert validation["reference_data"] is True

    def test_validate_missing_variables(self, resolver):
        """Test validation of missing variables."""
        template = "{{input_data.missing}} and {{nonexistent}}"
        validation = resolver.validate_variables(template)
        assert validation["input_data.missing"] is False
        assert validation["nonexistent"] is False

    def test_get_missing_variables(self, resolver):
        """Test getting list of missing variables."""
        template = "{{input_data.vendor_name}} {{missing}} {{input_data.nope}}"
        missing = resolver.get_missing_variables(template)
        assert set(missing) == {"missing", "input_data.nope"}

    # ==========================================================================
    # Integration Tests
    # ==========================================================================

    def test_complete_vendor_matching_template(self, resolver):
        """Test complete vendor matching template from spec."""
        template = """Match vendor "{{input_data.vendor_name}}" from:
{{reference_data}}

Contract value: {{input_data.contract_value}}
Region: {{input_data.metadata.region}}"""

        result = resolver.resolve(template)

        # Verify all variables were replaced correctly
        assert "Slack India Pvt Ltd" in result
        assert "Canonical Vendors" in result
        assert "50000" in result
        assert "APAC" in result
        assert "{{" not in result  # No unresolved variables

    def test_complex_nested_template(self, resolver):
        """Test complex template with various variable types."""
        template = """Input Summary:
- Vendor: {{input_data.vendor_name}}
- Date: {{input_data.contract_date}}
- First Item: {{input_data.line_items.0.product}}
- Metadata: {{input_data.metadata}}
- Missing: {{input_data.nonexistent}}

Reference Database:
{{reference_data}}"""

        result = resolver.resolve(template)

        # Verify each part
        assert "Slack India Pvt Ltd" in result
        assert "2024-01-15" in result
        assert "Slack Pro" in result
        assert '"region": "APAC"' in result  # JSON serialized
        assert "Missing: \n" in result  # Empty for missing field
        assert "Canonical Vendors" in result
