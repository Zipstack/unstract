import json
import time

import pytest
from conftest import SEED_DATA, TEST_INDEX_NAME

from unstract.metrics import MetricsAggregator, capture_metrics


@pytest.mark.parametrize("input_file", SEED_DATA)
def test_add_metrics(metrics_agg: MetricsAggregator, mocker, es_client, input_file):
    with open(input_file) as file:
        mock_metrics = json.load(file)

    add_metrics_mock = mocker.patch.object(
        metrics_agg, "add_metrics", wraps=metrics_agg.add_metrics
    )
    metrics_agg.add_metrics(metrics=mock_metrics, index=TEST_INDEX_NAME)
    add_metrics_mock.assert_called_once_with(
        metrics=mock_metrics, index=TEST_INDEX_NAME
    )

    # Assert data in Elasticsearch
    es_client.indices.refresh(index=TEST_INDEX_NAME)
    result = es_client.search(index=TEST_INDEX_NAME, body={"query": {"match_all": {}}})

    # Assert if the record is in the index
    assert result["hits"]["total"]["value"] > 0
    indexed_doc = result["hits"]["hits"][0]["_source"]

    assert indexed_doc["org_id"] == mock_metrics["org_id"]
    assert indexed_doc["run_id"] == mock_metrics["run_id"]
    assert indexed_doc["project_id"] == mock_metrics["project_id"]
    assert indexed_doc["start_time"] == mock_metrics["start_time"]
    assert indexed_doc["end_time"] == mock_metrics["end_time"]
    assert indexed_doc["owner"] == mock_metrics["owner"]
    assert indexed_doc["agent"] == mock_metrics["agent"]
    assert indexed_doc["agent_name"] == mock_metrics["agent_name"]
    assert indexed_doc["agent_id"] == mock_metrics["agent_id"]
    assert indexed_doc["status"] == mock_metrics["status"]
    assert indexed_doc["api_key"] == mock_metrics["api_key"]


@pytest.mark.parametrize("input_file", SEED_DATA)
def test_query_metrics(metrics_agg: MetricsAggregator, mocker, es_client, input_file):
    with open(input_file) as file:
        mock_metrics = json.load(file)

    es_client.index(index=TEST_INDEX_NAME, body=mock_metrics, refresh=True)

    response = metrics_agg.query_metrics(
        run_id=mock_metrics["run_id"], index=TEST_INDEX_NAME
    )

    assert len(response["hits"]["hits"]) > 0
    queried_doc = response["hits"]["hits"][0]["_source"]

    assert queried_doc["org_id"] == mock_metrics["org_id"]
    assert queried_doc["run_id"] == mock_metrics["run_id"]
    assert queried_doc["project_id"] == mock_metrics["project_id"]
    assert queried_doc["start_time"] == mock_metrics["start_time"]
    assert queried_doc["end_time"] == mock_metrics["end_time"]
    assert queried_doc["owner"] == mock_metrics["owner"]
    assert queried_doc["agent"] == mock_metrics["agent"]
    assert queried_doc["agent_name"] == mock_metrics["agent_name"]
    assert queried_doc["agent_id"] == mock_metrics["agent_id"]
    assert queried_doc["status"] == mock_metrics["status"]
    assert queried_doc["api_key"] == mock_metrics["api_key"]


@pytest.mark.parametrize("input_file", SEED_DATA)
def test_metrics_capture(metrics_agg: MetricsAggregator, mocker, es_client, input_file):
    with open(input_file) as file:
        mock_metrics = json.load(file)

    @capture_metrics(index=TEST_INDEX_NAME, **mock_metrics)
    def waited_add(a, b):
        result = a + b
        time.sleep(1)
        return result

    waited_add(2, 3)
    # TODO: Make assertions
