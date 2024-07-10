from typing import Optional

from unstract.metrics.models.metrics import Metrics


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
