"""Workflow Service Components

This package contains specialized workflow service components for handling
workflow execution sources, destinations and related functionality.

Components:
- SourceConnector: Handles workflow input sources (filesystem, API storage, etc.)
- DestinationConnector: Handles workflow output destinations (database, filesystem, API, etc.)
"""

from .destination_connector import DestinationConfig, WorkerDestinationConnector
from .source_connector import SourceConfig, WorkerSourceConnector
from .workflow_utils import detect_comprehensive_workflow_type

__all__ = [
    "WorkerDestinationConnector",
    "DestinationConfig",
    "WorkerSourceConnector",
    "SourceConfig",
    "detect_comprehensive_workflow_type",
]
