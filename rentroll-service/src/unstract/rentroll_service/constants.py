# constants.py
"""Constants for the RentRoll Extractor plugin."""

from enum import Enum


class RentRollExtractorKeys(str, Enum):
    """Keys used in the rent roll extractor settings."""

    # Input/Output
    INPUT_FILE = "input_file"
    OUTPUT_FILE = "output_file"

    # Schema and Configuration
    SCHEMA = "schema"
    ENABLE_HIGHLIGHT = "enable_highlight"
    TAGS = "tags"
    USE_FORM_FEED = "use_form_feed"
    PROMPT = "prompt"


# Default schema for rent roll data
DEFAULT_SCHEMA = {
    "type": "object",
    "properties": {
        "unit": {"type": "string", "description": "Unit identifier"},
        "unit_type": {"type": "string", "description": "Type of unit"},
        "area": {"type": "number", "description": "Area in square feet"},
        "tenant_name": {"type": "string", "description": "Name of tenant"},
        "rent": {"type": "number", "description": "Monthly rent amount"},
        "lease_start": {
            "type": "string",
            "format": "date",
            "description": "Lease start date",
        },
        "lease_end": {
            "type": "string",
            "format": "date",
            "description": "Lease end date",
        },
    },
    "required": ["unit", "unit_type", "area", "rent"],
}

USER_FIELDS = {
    "property_type": None,
    "unit_ref_id": None,
    "unit_type": None,
    "area": None,
    "tenant_ref_id": None,
    "tenant_name": None,
    "market_rent": None,
    "charge_codes": None,
    "charge_codes[0].charge_code": None,
    "charge_codes[0].value": None,
    "lease_start_date": None,
    "lease_end_date": None,
    "unit_area_measured_by": None,
    "num_parking_spaces": None,
    "num_rooms": None,
    "num_bath_rooms": None,
    "rented_status": None,
    "rent_annual": None,
    "rent_quarterly": None,
    "rent_monthly": None,
    "rent_parking_annual": None,
    "source_rent_parking_quarterly": None,
    "source_rent_parking_monthly": None,
}
