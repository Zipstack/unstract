import os
import unittest
from typing import Any
from unittest.mock import patch

import yaml

from unstract.tool_registry import ToolRegistry
from unstract.tool_registry.constants import Command
from unstract.tool_registry.helper import ToolRegistryHelper


# TODO: Fix breaking test cases due to code restructuring
class TestToolRegistry(unittest.TestCase):
    registry: ToolRegistry
    REGISTRY_FILE = "test_registry_file.yaml"
    TOOLS_FILE = "test_tools.json"
    TEST_TOOL_ID = "document_indexer"
    TEST_IMAGE_URL = "local:indexer"
    mock_run_tool_and_get_logs: Any

    @classmethod
    def setUpClass(self) -> None:
        test_registry_content = {
            "document": "unstract-tool-registry",
            "tools": [self.TEST_IMAGE_URL],
        }
        directory = os.path.dirname(os.path.abspath(__file__))
        registry_file_path = os.path.join(directory, TestToolRegistry.REGISTRY_FILE)
        with open(registry_file_path, "w") as yaml_file:
            yaml.dump(test_registry_content, yaml_file, default_flow_style=False)

        # Apply the patch to 'run_tool_and_get_logs' before each test method
        self.mock_run_tool_and_get_logs = patch.object(
            ToolRegistryHelper,
            "run_tool_and_get_logs",
            side_effect=self.mocked_run_tool_and_get_logs,
        )
        self.mock_run_tool_and_get_logs.start()

        self.registry = ToolRegistry(
            private_tools=TestToolRegistry.TOOLS_FILE,
            registry_file=TestToolRegistry.REGISTRY_FILE,
        )
        self.registry.load_all_tools_to_disk()

    @classmethod
    def tearDownClass(self) -> None:
        self.mock_run_tool_and_get_logs.stop()
        directory = os.path.dirname(os.path.abspath(__file__))
        registry = os.path.join(directory, TestToolRegistry.REGISTRY_FILE)
        tools_file = os.path.join(directory, TestToolRegistry.TOOLS_FILE)
        if os.path.exists(tools_file):
            os.remove(tools_file)
            print(f"{tools_file} has been deleted.")
        else:
            print(f"{tools_file} does not exist.")

        if os.path.exists(registry):
            os.remove(registry)
            print(f"{registry} has been deleted.")
        else:
            print(f"{registry} does not exist.")

    @classmethod
    def mocked_run_tool_and_get_logs(
        self, command: str, tool_meta: dict[str, Any]
    ) -> Any:
        if command == Command.SPEC:
            return {"title": "Document Indexer"}
        elif command == Command.PROPERTIES:
            return {
                "display_name": "Document Indexer",
                "function_name": self.TEST_TOOL_ID,
            }
        elif command == Command.ICON:
            return ""

    def test_list_tools_urls(self) -> None:
        tools = self.registry.list_tools_urls()
        self.assertIsInstance(tools, list)
        self.assertGreater(len(tools), 0)

    def test_fetch_all_tools(self) -> None:
        tools = self.registry.fetch_all_tools()
        self.assertIsNotNone(tools)
        self.assertEqual(len(tools) > 0, True)

    def test_get_tool_properties_by_tool_id(self) -> None:
        tool_id = "document_indexer"
        properties = self.registry.get_tool_properties_by_tool_id(tool_id=tool_id)
        self.assertIsNotNone(properties)
        self.assertEqual(properties.get("function_name"), tool_id)

    def test_get_tool_spec_by_tool_id(self) -> None:
        tool_id = "document_indexer"
        spec = self.registry.get_tool_spec_by_tool_id(tool_id=tool_id)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.get("title"))

    def test_add_and_remove_tool(self) -> None:
        tool_id = "fileops"
        image_url = "local:fileops"
        self.registry.remove_tool_by_uid(tool_id=tool_id)
        tools1 = self.registry.list_tools_urls()
        self.assertEqual(len(tools1), 1)
        self.registry.add_new_tool_by_image_url(image_url=image_url)
        tools2 = self.registry.list_tools_urls()
        self.assertEqual(len(tools2), 2)


if __name__ == "__main__":
    unittest.main()
