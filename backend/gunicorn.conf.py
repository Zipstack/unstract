import os
from uuid import uuid4

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_INSTANCE_ID, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# your gunicorn config here
# bind = "127.0.0.1:8000"

# Retrieve the collector endpoint from the environment variable
collector_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")


def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)
    if not collector_endpoint:
        return
    resource = Resource.create(
        attributes={
            # each worker needs a unique service.instance.id to distinguish the created metrics in prometheus
            SERVICE_INSTANCE_ID: str(uuid4()),
            "worker": worker.pid,
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=collector_endpoint))
    )
    trace.set_tracer_provider(tracer_provider)
