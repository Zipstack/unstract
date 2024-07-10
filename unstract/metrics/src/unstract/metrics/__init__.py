import os

from elasticsearch_dsl import connections

from .metrics import MetricsAggregator  # noqa: F401

ES_URL = os.getenv("ES_URL")
ES_CLOUD_ID = os.getenv("ES_CLOUD_ID")
ES_API_KEY = os.getenv("ES_API_KEY")
if not ES_URL or (ES_CLOUD_ID and ES_API_KEY):
    raise ValueError(
        "Either env ES_URL or ES_CLOUD_ID and ES_API_KEY "
        "is required to import unstract-metrics"
    )

connections.create_connection(hosts=[ES_URL], cloud_id=ES_CLOUD_ID, api_key=ES_API_KEY)
