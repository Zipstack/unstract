import operator
from typing import Any


class ResultKeys:
    METADATA = "metadata"
    CONFIDENCE_DATA = "confidence_data"
    OUTPUT = "output"


def _check_confidence(field_entries, threshold):
    """Check if any confidence value meets or exceeds the threshold."""
    return any(
        float(entry.get("confidence", 0)) * 100 >= threshold
        for entries in field_entries
        if entries
        for entry in entries
        if "confidence" in entry
    )


def _get_field_value(context: dict[str, Any], keys: list[str]) -> Any:
    """Retrieve nested field value using dot notation keys."""
    field_value = context.get(ResultKeys.OUTPUT, {})
    for key in keys:
        if isinstance(field_value, dict):
            field_value = field_value.get(key, {})
        else:
            return None
    return field_value


def _evaluate_rule(rule: dict[str, Any], context: dict[str, Any]) -> bool:
    """Evaluate a single rule against the context."""
    operator_map = {
        "less": operator.lt,
        "greater": operator.gt,
        "equal": operator.eq,
        "not_equal": operator.ne,
        "less_or_equal": operator.le,
        "greater_or_equal": operator.ge,
        "starts_with": lambda field, value: str(field).startswith(value),
        "ends_with": lambda field, value: str(field).endswith(value),
        "like": lambda field, value: value in str(field),
        "not_like": lambda field, value: value not in str(field),
    }

    field = rule["properties"]["field"]
    operator_name = rule["properties"]["operator"]
    value = rule["properties"]["value"][0]
    keys = field.split(".")

    if keys[0] == "jsonField":
        field_value = _get_field_value(context, keys[1:])
    elif keys[0] == "confidence":
        confidence_data = context.get(ResultKeys.METADATA, {}).get(
            ResultKeys.CONFIDENCE_DATA, {}
        )
        field_entries = confidence_data.get(keys[1], [])
        return _check_confidence(field_entries, value)
    else:
        return False

    try:
        if isinstance(field_value, bool):
            field_value = str(field_value).lower()
            value = str(value).lower()
        return operator_map[operator_name](field_value, value)
    except Exception as e:
        print(f"Error evaluating rule: {e}")
        return False


def _evaluate_group(group: dict[str, Any], context: dict[str, Any]) -> bool:
    """Evaluate a group of rules or nested groups."""
    conjunction = group["properties"].get("conjunction", "and").lower()
    negate = group["properties"].get("not", False)

    results = []
    for child in group.get("children1", []):
        if child["type"] == "rule":
            results.append(_evaluate_rule(child, context))
        elif child["type"] in ["group", "rule_group"]:
            results.append(_evaluate_group(child, context))

    result = all(results) if conjunction == "and" else any(results)
    return not result if negate else result


rules_json = {
    "type": "group",
    "id": "b88b8b8b-89ab-4cde-b012-31958e37dae3",
    "children1": [
        {
            "type": "rule_group",
            "id": "989ab9b8-0123-4456-b89a-b1958e37e4a8",
            "properties": {
                "conjunction": "AND",
                "not": False,
                "field": "jsonField.newrule_2",
                "fieldSrc": "field",
            },
            "children1": [
                {
                    "type": "rule",
                    "id": "9a89a8b9-89ab-4cde-b012-31958e7d3ee2",
                    "properties": {
                        "fieldSrc": "field",
                        "field": "jsonField.newrule_2.city",
                        "operator": "equal",
                        "value": ["Cannanore"],
                        "valueSrc": ["value"],
                        "valueType": ["text"],
                        "valueError": [None],
                    },
                }
            ],
        }
    ],
    "properties": {"conjunction": "AND", "not": False},
}

result = {
    "output": {
        "newrule_1": "Mr. Vishnu Sathyanesan",
        "newrule_2": {
            "address": "165/26, Panjanyan, West Thayinari Kara Road",
            "city": "Cannanore",
            "district": "Kannur",
        },
    }
}

print(_evaluate_group(rules_json, result))
