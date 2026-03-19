"""Preprocessing/postprocessing hooks for drf-spectacular schema generation.

Filters the OpenAPI spec to include only the Platform API endpoints
specified in the API reference documentation.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Exact path+method pairs to include.
# Each entry is (regex_pattern, set_of_allowed_methods).
# Methods not listed are excluded (notably DELETE is excluded everywhere).
ALLOWED_ENDPOINTS: list[tuple[re.Pattern[str], set[str]]] = [
    # --- Prompt Studio ---
    (re.compile(r"/prompt-studio/$"), {"GET", "POST"}),
    (re.compile(r"/prompt-studio/[^/]+/$"), {"GET", "PATCH", "PUT"}),
    (re.compile(r"/prompt-studio/project-transfer/$"), {"POST"}),
    (re.compile(r"/prompt-studio/project-transfer/[^/]+$"), {"GET", "POST"}),
    (re.compile(r"/prompt-studio/export/[^/]+$"), {"GET", "POST"}),
    (re.compile(r"/prompt-studio/select_choices/$"), {"GET"}),
    (re.compile(r"/prompt-studio/[^/]+/get_retrieval_strategies/$"), {"GET"}),
    (re.compile(r"/prompt-studio/prompt-studio-profile/[^/]+/$"), {"GET", "PATCH"}),
    (re.compile(r"/prompt-studio/profilemanager/[^/]+$"), {"POST"}),
    (re.compile(r"/prompt-studio/prompt-studio-prompt/[^/]+/$"), {"POST"}),
    (re.compile(r"/prompt-studio/index-document/[^/]+$"), {"POST"}),
    (re.compile(r"/prompt-studio/fetch_response/[^/]+$"), {"POST"}),
    (re.compile(r"/prompt-studio/single-pass-extraction/[^/]+$"), {"POST"}),
    (re.compile(r"/prompt-studio/file/[^/]+$"), {"GET", "POST"}),
    (re.compile(r"/prompt-studio/users/[^/]+$"), {"GET"}),
    (re.compile(r"/prompt-studio/[^/]+/check_deployment_usage/$"), {"GET"}),
    # --- Workflows ---
    (re.compile(r"/workflow/$"), {"GET", "POST"}),
    (re.compile(r"/workflow/[^/]+/$"), {"GET", "PATCH", "PUT"}),
    (re.compile(r"/workflow/execute/$"), {"POST"}),
    (re.compile(r"/workflow/active/[^/]+/$"), {"PUT"}),
    (re.compile(r"/workflow/[^/]+/can-update/$"), {"GET"}),
    (re.compile(r"/workflow/[^/]+/clear-file-marker/$"), {"GET"}),
    (re.compile(r"/workflow/schema/$"), {"GET"}),
    (re.compile(r"/workflow/[^/]+/users/$"), {"GET"}),
    (re.compile(r"/workflow/[^/]+/execution/$"), {"GET"}),
    (re.compile(r"/workflow/execution/[^/]+/$"), {"GET"}),
    (re.compile(r"/workflow/execution/[^/]+/logs/$"), {"GET"}),
    (re.compile(r"/workflow/[^/]+/file-histories/$"), {"GET"}),
    (re.compile(r"/workflow/[^/]+/file-histories/[^/]+/$"), {"GET"}),
    (re.compile(r"/workflow/[^/]+/file-histories/clear/$"), {"POST"}),
    # --- API Deployments ---
    (re.compile(r"/api/deployment/$"), {"GET", "POST"}),
    (re.compile(r"/api/deployment/[^/]+/$"), {"GET", "PATCH", "PUT"}),
    (re.compile(r"/api/deployment/[^/]+/users/$"), {"GET"}),
    (re.compile(r"/api/deployment/by-prompt-studio-tool/$"), {"GET"}),
    (re.compile(r"/api/postman_collection/[^/]+/$"), {"GET"}),
    (re.compile(r"/api/keys/api/$"), {"GET", "POST"}),
    (re.compile(r"/api/keys/api/[^/]+/$"), {"GET", "POST"}),
    (re.compile(r"/api/keys/[^/]+/$"), {"GET", "PUT"}),
    # --- Pipelines ---
    (re.compile(r"/pipeline/$"), {"GET", "POST"}),
    (re.compile(r"/pipeline/[^/]+/$"), {"GET", "PATCH", "PUT"}),
    (re.compile(r"/pipeline/execute/$"), {"POST"}),
    (re.compile(r"/pipeline/[^/]+/executions/$"), {"GET"}),
    (re.compile(r"/pipeline/[^/]+/users/$"), {"GET"}),
    (re.compile(r"/pipeline/api/postman_collection/[^/]+/$"), {"GET"}),
    (re.compile(r"/api/keys/pipeline/$"), {"GET", "POST"}),
    (re.compile(r"/api/keys/pipeline/[^/]+/$"), {"GET", "POST"}),
    # --- Adapters ---
    (re.compile(r"/adapter/$"), {"GET", "POST"}),
    (re.compile(r"/adapter/[^/]+/$"), {"GET", "PATCH", "PUT"}),
    (re.compile(r"/adapter/info/[^/]+/$"), {"GET"}),
    (re.compile(r"/adapter/users/[^/]+/$"), {"GET"}),
    (re.compile(r"/adapter/default_triad/$"), {"GET", "POST"}),
    (re.compile(r"/supported_adapters/$"), {"GET"}),
    (re.compile(r"/adapter_schema/$"), {"GET"}),
    (re.compile(r"/test_adapters/$"), {"POST"}),
    # --- Connectors ---
    (re.compile(r"/connector/$"), {"GET", "POST"}),
    (re.compile(r"/connector/[^/]+/$"), {"GET", "PATCH", "PUT"}),
]

# Paths to always exclude (takes priority over ALLOWED_ENDPOINTS)
EXCLUDED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\{format\}"),
    re.compile(r"adapter-choices"),
    re.compile(r"/internal/"),
    re.compile(r"/manual_review/"),
    re.compile(r"/notifications/"),
    re.compile(r"/document-index"),
    re.compile(r"/prompt-document"),
    re.compile(r"/prompt-output"),
    re.compile(r"/registry/"),
    re.compile(r"/tool/prompt-studio"),
    re.compile(r"/workflow/endpoint"),
    re.compile(r"/public/"),
]


def filter_endpoints(endpoints: list[tuple]) -> list[tuple]:
    """Whitelist-based filter: only include endpoints explicitly listed."""
    filtered = []
    for endpoint in endpoints:
        path = endpoint[0]
        method = endpoint[2].upper() if len(endpoint) > 2 else ""

        if any(pat.search(path) for pat in EXCLUDED_PATTERNS):
            continue

        for pattern, methods in ALLOWED_ENDPOINTS:
            if pattern.search(path) and method in methods:
                filtered.append(endpoint)
                break

    logger.info(
        "Schema filter: %d/%d endpoints included",
        len(filtered),
        len(endpoints),
    )
    return filtered


def strip_version_suffix(result: dict, **kwargs) -> dict:
    """Remove DRF request version suffix (e.g. '1.0.0 (v1)' -> '1.0.0')."""
    version = result.get("info", {}).get("version", "")
    if " (" in version:
        result["info"]["version"] = version.split(" (")[0]
    return result
