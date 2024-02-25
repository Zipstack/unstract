import io

from unstract.sdk.tool.base import BaseTool
from unstructured.partition.auto import partition


class ClassifierHelper:
    """Helper functions for Classifier."""

    def __init__(self, tool: BaseTool) -> None:
        self.tool = tool

    def extract_text(self, file: str) -> str:
        """Extract text from file.

        Args:
            file (str): The path to the input file

        Returns:
            str: page content
        """
        try:
            with open(file, mode="rb") as input_file_obj:
                bytes_io = io.BytesIO(input_file_obj.read())
                elements = partition(file=bytes_io)
        except Exception as e:
            self.tool.stream_error_and_exit(f"Error partitioning file: {e}")
        text = "\n\n".join([str(el) for el in elements])
        return text
