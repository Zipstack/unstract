"""Digraph generation module for Autogen GraphFlow.

This module provides celery tasks for generating directed graphs that can be used
with Microsoft Autogen's GraphFlow for orchestrating multi-agent data extraction.
"""

from .digraph_task import execute_graph_flow, generate_extraction_digraph
from .executor import execute_extraction_workflow, validate_graph_flow_data
from .spec_parser import ExtractionSpecParser

__all__ = [
    "generate_extraction_digraph",
    "execute_graph_flow",
    "ExtractionSpecParser",
    "execute_extraction_workflow",
    "validate_graph_flow_data",
]

# Celery task registration information
CELERY_TASKS = {
    "generate_extraction_digraph": {
        "task": generate_extraction_digraph,
        "name": "generate_extraction_digraph",
        "queue": "processing_queue",
        "routing_key": "digraph.generation",
        "priority": 6,  # Higher than chunking
        "rate_limit": "50/m",
        "time_limit": 600,  # 10 minutes
        "soft_time_limit": 540,  # 9 minutes
    }
}

# Module metadata
__version__ = "0.1.0"
__author__ = "Unstract Team"
__description__ = "Autogen digraph generation for data extraction workflows"
