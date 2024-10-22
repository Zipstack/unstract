import functools
import json
import logging
import os
from datetime import datetime
from typing import Optional
from uuid import uuid4

from unstract.metrics.constants import MetricsConstants, MetricsEnv
from unstract.metrics.models.metrics import Metrics

logger = logging.getLogger(__name__)


class MetricsAggregator:

    def __init__(self, index_to_clone: Optional[str] = None) -> None:
        # TODO: Create index with dynamic templates through a separate command
        if not Metrics._index.exists():
            Metrics.init(index=index_to_clone)

    def add_metrics(self, metrics, index: str = "unstract-metrics-0"):
        metrics_doc = Metrics(**metrics)
        metrics_doc.save(index=index)

    def query_metrics(self, run_id: str, index: str = "unstract-metrics-0"):
        s = Metrics.search(index=index).query("match", run_id=run_id)
        response = s.execute()
        return response.to_dict()


def capture_metrics(index="unstract-metrics-0", **metric_kwargs):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):

            if (
                os.getenv(MetricsEnv.COLLECT_UNSTRACT_METRICS, "False").lower()
                == "false"
            ):
                return func(*args, **kwargs)

            logger.debug(
                f"Collecting metrics with kwargs: {json.dumps(metric_kwargs, indent=2)}"
            )
            metrics = Metrics(**metric_kwargs)
            if not metrics.run_id:
                metrics.run_id = uuid4()
            metrics.start_time = datetime.now().strftime(
                MetricsConstants.DATETIME_FORMAT
            )
            try:
                result = func(*args, **kwargs)
            finally:
                metrics.end_time = datetime.now().strftime(
                    MetricsConstants.DATETIME_FORMAT
                )
                metrics.save(index=index)
            return result

        return wrapper

    return decorator
