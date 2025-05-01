import importlib
import inspect
from typing import Dict, List, Type

from prompt_studio.processors.base_processor import BaseProcessor
from prompt_studio.allowed_processors import ALLOWED_PROCESSORS


def get_processor_class(processor_type: str) -> Type[BaseProcessor]:
    """
    Get the processor class for the given processor type.

    Args:
        processor_type: The type of processor to get.

    Returns:
        The processor class.

    Raises:
        ValueError: If the processor type is not found or not allowed.
    """
    # Convert processor type to module path
    module_path = f"prompt_studio.processors.{processor_type}_processor"
    
    # Check if the module path is in the allowed list
    if module_path not in ALLOWED_PROCESSORS:
        raise ValueError(f"Processor type '{processor_type}' is not allowed")
    
    try:
        module = importlib.import_module(module_path)
        for name, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseProcessor)
                and obj != BaseProcessor
            ):
                return obj
        raise ValueError(f"No processor class found for type '{processor_type}'")
    except ImportError:
        raise ValueError(f"Processor type '{processor_type}' not found")


def get_processor_types() -> List[str]:
    """
    Get the list of available processor types.

    Returns:
        The list of processor types.
    """
    processor_types = []
    for module_path in ALLOWED_PROCESSORS:
        if module_path.startswith("prompt_studio.processors.") and module_path.endswith("_processor"):
            processor_type = module_path.split(".")[-1].replace("_processor", "")
            if processor_type != "base":  # Skip the base processor
                processor_types.append(processor_type)
    return processor_types
