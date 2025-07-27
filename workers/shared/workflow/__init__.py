"""Workflow Service Components

This package contains specialized workflow service components for handling
workflow execution destinations and related functionality.

Components:
- DestinationConnector: Handles workflow output destinations (database, filesystem, API, etc.)
"""

from .destination_connector import DestinationConfig, WorkerDestinationConnector

__all__ = [
    "WorkerDestinationConnector",
    "DestinationConfig",
]
