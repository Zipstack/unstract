"""Regression tests for api_v2.postman_collection.dto — the builder that
turns an API deployment or pipeline into a Postman v2.1 collection.

UN-2190: the execute request gained a post-response capture script and the
status request reuses the captured ``execution_id`` collection variable.
These tests pin the contract so a refactor can't reopen the gaps the
review flagged: the null-event strip, the variable/URL/JS all referencing
the SAME constant, and the status URL keeping ``{{execution_id}}`` literal
(not percent-encoded).

The DTOs are constructed directly (no DB) and only ``WEB_APP_ORIGIN_URL``
is overridden, so the suite is cheap and needs no fixtures.
"""

from __future__ import annotations

import pytest
from django.test import override_settings

from api_v2.postman_collection.constants import CollectionKey
from api_v2.postman_collection.dto import (
    APIDeploymentDto,
    PipelineDto,
    PostmanCollection,
)

WEB_APP_ORIGIN_URL = "https://example.unstract.com"
API_ENDPOINT = "deployment/api/org/my-api/"
API_KEY = "test-api-key"


def _api_deployment_dto() -> APIDeploymentDto:
    return APIDeploymentDto(
        display_name="My API",
        description="An API deployment",
        api_endpoint=API_ENDPOINT,
        api_key=API_KEY,
    )


def _pipeline_dto() -> PipelineDto:
    return PipelineDto(
        pipeline_name="My Pipeline",
        api_endpoint=API_ENDPOINT,
        api_key=API_KEY,
    )


def _build_dict(data_object) -> dict:
    """Mirror PostmanCollection.create without touching the DB.

    Pins WEB_APP_ORIGIN_URL so URL building is deterministic regardless of
    the ambient test settings.
    """
    with override_settings(WEB_APP_ORIGIN_URL=WEB_APP_ORIGIN_URL):
        collection = PostmanCollection(
            info=data_object.get_postman_info(),
            item=data_object.get_postman_items(),
            variable=data_object.get_collection_variables(),
        )
        return collection.to_dict()


def _item_by_name(collection_dict: dict, name: str) -> dict:
    for item in collection_dict["item"]:
        if item["name"] == name:
            return item
    raise AssertionError(f"item {name!r} not found in collection")


class TestApiDeploymentCollection:
    def test_execute_item_keeps_populated_event(self) -> None:
        """to_dict keeps the populated execute event and its capture script."""
        collection_dict = _build_dict(_api_deployment_dto())
        execute_item = _item_by_name(collection_dict, CollectionKey.EXECUTE_API_KEY)

        assert "event" in execute_item
        assert execute_item["event"], "execute event must not be stripped"
        script_lines = execute_item["event"][0]["script"]["exec"]
        joined = "\n".join(script_lines)
        # The capture must target the same constant the variable/URL use.
        assert (
            f'pm.collectionVariables.set("{CollectionKey.EXEC_ID_VARIABLE_NAME}"'
            in joined
        )

    def test_capture_script_resets_on_missing_execution_id(self) -> None:
        """The else branch resets to the sentinel so a stale id is never reused."""
        collection_dict = _build_dict(_api_deployment_dto())
        execute_item = _item_by_name(collection_dict, CollectionKey.EXECUTE_API_KEY)
        joined = "\n".join(execute_item["event"][0]["script"]["exec"])

        assert "else" in joined
        assert (
            f'pm.collectionVariables.set("{CollectionKey.EXEC_ID_VARIABLE_NAME}", '
            f'"{CollectionKey.STATUS_EXEC_ID_DEFAULT}")' in joined
        )
        assert "console.warn" in joined

    def test_status_item_has_no_event_key(self) -> None:
        """The status request carries no scripts -> no 'event' key at all."""
        collection_dict = _build_dict(_api_deployment_dto())
        status_item = _item_by_name(collection_dict, CollectionKey.STATUS_API_KEY)
        assert "event" not in status_item

    def test_variable_array_references_the_constant(self) -> None:
        """The collection 'variable' array exposes the exec-id variable."""
        collection_dict = _build_dict(_api_deployment_dto())
        variables = collection_dict["variable"]
        assert any(
            v["key"] == CollectionKey.EXEC_ID_VARIABLE_NAME for v in variables
        )

    def test_status_url_keeps_unencoded_variable_reference(self) -> None:
        """Status URL keeps execution_id={{execution_id}} literal, not %7B-encoded."""
        collection_dict = _build_dict(_api_deployment_dto())
        status_item = _item_by_name(collection_dict, CollectionKey.STATUS_API_KEY)
        url = status_item["request"]["url"]

        assert (
            f"{CollectionKey.EXEC_ID_VARIABLE_NAME}="
            f"{CollectionKey.STATUS_EXEC_ID_VARIABLE}" in url
        )
        assert "%7B" not in url and "%7D" not in url


class TestCollectionShapeRegression:
    def test_pipeline_carries_no_event_and_empty_variable(self) -> None:
        """PipelineDto: no scripts and no collection variables."""
        collection_dict = _build_dict(_pipeline_dto())
        assert collection_dict["variable"] == []
        for item in collection_dict["item"]:
            assert "event" not in item

    def test_api_deployment_carries_event_and_variable(self) -> None:
        """APIDeploymentDto: execute event present and variable populated."""
        collection_dict = _build_dict(_api_deployment_dto())
        execute_item = _item_by_name(collection_dict, CollectionKey.EXECUTE_API_KEY)
        assert execute_item.get("event")
        assert collection_dict["variable"], "api deployment must expose variables"


class TestConstantCoupling:
    def test_status_variable_derived_from_name(self) -> None:
        """STATUS_EXEC_ID_VARIABLE must be the {{...}} form of the var name."""
        assert (
            CollectionKey.STATUS_EXEC_ID_VARIABLE
            == f"{{{{{CollectionKey.EXEC_ID_VARIABLE_NAME}}}}}"
        )
        assert CollectionKey.STATUS_EXEC_ID_VARIABLE == "{{execution_id}}"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
