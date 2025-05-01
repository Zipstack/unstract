import importlib
import inspect
import os
from typing import Dict, List, Optional, Type

from prompt_studio.modifiers.base import BaseModifier
from prompt_studio.modifiers.registry import ModifierRegistry


class ModifierLoader:
    """
    Loads modifiers from a directory.
    """

    def __init__(self, registry: ModifierRegistry):
        self.registry = registry

    def load_modifiers_from_directory(self, directory: str) -> None:
        """
        Loads modifiers from a directory.
        """
        for root, _, files in os.walk(directory):
            for file in files:
                if file.endswith(".py") and not file.startswith("__"):
                    module_path = os.path.join(root, file)
                    module_name = self._get_module_name(module_path, directory)
                    self._load_modifier_from_module(module_name)

    def _get_module_name(self, module_path: str, base_dir: str) -> str:
        """
        Gets the module name from a module path.
        """
        rel_path = os.path.relpath(module_path, base_dir)
        module_name = rel_path.replace(os.path.sep, ".").replace(".py", "")
        return module_name

    def _load_modifier_from_module(self, module_name: str) -> None:
        """
        Loads a modifier from a module.
        """
        # Security fix: Implement a whitelist of allowed module prefixes
        allowed_prefixes = [
            "prompt_studio.modifiers.",
            "modifiers.",
        ]
        
        # Check if the module name is in the allowed prefixes
        if not any(module_name.startswith(prefix) for prefix in allowed_prefixes):
            print(f"Warning: Skipping module {module_name} as it's not in the allowed prefixes")
            return
            
        try:
            module = importlib.import_module(module_name)
            self._register_modifiers_from_module(module)
        except (ImportError, AttributeError) as e:
            print(f"Error loading module {module_name}: {e}")

    def _register_modifiers_from_module(self, module) -> None:
        """
        Registers modifiers from a module.
        """
        for _, obj in inspect.getmembers(module):
            if (
                inspect.isclass(obj)
                and issubclass(obj, BaseModifier)
                and obj != BaseModifier
            ):
                self.registry.register_modifier(obj)
