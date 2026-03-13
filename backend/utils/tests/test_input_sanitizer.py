import pytest
from rest_framework.serializers import ValidationError

from utils.input_sanitizer import validate_name_field, validate_no_html_tags


class TestValidateNoHtmlTags:
    def test_clean_input_passes(self):
        assert validate_no_html_tags("Hello World") == "Hello World"

    def test_allows_normal_special_chars(self):
        assert (
            validate_no_html_tags("My workflow (v2), test - final")
            == "My workflow (v2), test - final"
        )

    def test_allows_numbers_and_punctuation(self):
        assert validate_no_html_tags("Test 123 & more!") == "Test 123 & more!"

    def test_rejects_script_tag(self):
        with pytest.raises(ValidationError, match="must not contain HTML or script tags"):
            validate_no_html_tags("<script>alert(1)</script>")

    def test_rejects_img_tag(self):
        with pytest.raises(ValidationError, match="must not contain HTML or script tags"):
            validate_no_html_tags('<img src=x onerror=alert(1)>')

    def test_rejects_div_tag(self):
        with pytest.raises(ValidationError, match="must not contain HTML or script tags"):
            validate_no_html_tags("<div>content</div>")

    def test_rejects_self_closing_tag(self):
        with pytest.raises(ValidationError, match="must not contain HTML or script tags"):
            validate_no_html_tags("<br/>")

    def test_rejects_javascript_protocol(self):
        with pytest.raises(ValidationError, match="must not contain JavaScript protocols"):
            validate_no_html_tags("javascript:alert(1)")

    def test_rejects_javascript_protocol_with_spaces(self):
        with pytest.raises(ValidationError, match="must not contain JavaScript protocols"):
            validate_no_html_tags("javascript :alert(1)")

    def test_rejects_javascript_protocol_case_insensitive(self):
        with pytest.raises(ValidationError, match="must not contain JavaScript protocols"):
            validate_no_html_tags("JAVASCRIPT:alert(1)")

    def test_rejects_event_handler(self):
        with pytest.raises(
            ValidationError, match="must not contain event handler attributes"
        ):
            validate_no_html_tags("onclick=alert(1)")

    def test_rejects_event_handler_with_spaces(self):
        with pytest.raises(
            ValidationError, match="must not contain event handler attributes"
        ):
            validate_no_html_tags("onerror =alert(1)")

    def test_rejects_event_handler_case_insensitive(self):
        with pytest.raises(
            ValidationError, match="must not contain event handler attributes"
        ):
            validate_no_html_tags("ONLOAD=alert(1)")

    def test_custom_field_name_in_error(self):
        with pytest.raises(ValidationError, match="Workflow name"):
            validate_no_html_tags("<script>", field_name="Workflow name")


class TestValidateNameField:
    def test_clean_name_passes(self):
        assert validate_name_field("My Workflow") == "My Workflow"

    def test_strips_whitespace(self):
        assert validate_name_field("  hello  ") == "hello"

    def test_rejects_empty_after_strip(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            validate_name_field("   ")

    def test_rejects_html_tags(self):
        with pytest.raises(ValidationError, match="must not contain HTML or script tags"):
            validate_name_field("<script>alert(1)</script>")

    def test_allows_hyphens_and_underscores(self):
        assert validate_name_field("my-workflow_v2") == "my-workflow_v2"

    def test_allows_periods(self):
        assert validate_name_field("config.v2") == "config.v2"

    def test_allows_parentheses_and_commas(self):
        assert validate_name_field("Test (v2), final") == "Test (v2), final"

    def test_custom_field_name_in_error(self):
        with pytest.raises(ValidationError, match="Tool name"):
            validate_name_field("   ", field_name="Tool name")
