import pytest
from elasticsearch import Elasticsearch

from unstract.metrics import MetricsAggregator

TEST_INDEX_NAME = "unstract-metrics-test"


@pytest.fixture(scope="module")
def es_client():
    client = Elasticsearch(hosts=["http://localhost:9200"])
    yield client
    client.options(ignore_status=[400, 404]).indices.delete(index=TEST_INDEX_NAME)


@pytest.fixture
def metrics_agg():
    yield MetricsAggregator()
