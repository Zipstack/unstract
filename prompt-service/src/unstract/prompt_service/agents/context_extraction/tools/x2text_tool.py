"""
X2Text Tool for Context Extraction Agent.
Wraps the X2Text functionality as a tool for use by the AutoGen agents.
"""
from typing import Any, Dict, List, Optional
import logging

from unstract.sdk.x2txt import TextExtractionResult, X2Text
from unstract.sdk.adapters.exceptions import AdapterError

logger = logging.getLogger(__name__)

class X2TextTool:
    """Tool that wraps X2Text to be used by AutoGen agents."""
    
    def __init__(self, x2text_instance: X2Text, fs=None):
        """
        Initialize the X2Text tool.
        
        Args:
            x2text_instance: The X2Text instance to use for document processing.
            fs: Optional filesystem instance for file operations.
        """
        self.x2text = x2text_instance
        self.fs = fs
    
    def process_document(self, input_file_path: str, output_file_path: Optional[str] = None, 
                       enable_highlight: bool = False, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Process document using X2Text and return extracted text.
        
        Args:
            input_file_path: Path to the input document.
            output_file_path: Optional path to save the output.
            enable_highlight: Whether to enable highlighting in the output.
            tags: Optional tags to associate with the document.
            
        Returns:
            Dictionary containing the extracted text and metadata.
        """
        try:
            process_response: TextExtractionResult = self.x2text.process(
                input_file_path=input_file_path,
                output_file_path=output_file_path,
                enable_highlight=enable_highlight,
                tags=tags,
                fs=self.fs
            )
            return {
                "extracted_text": process_response.extracted_text,
                "metadata": process_response.extraction_metadata.__dict__ if hasattr(process_response, "extraction_metadata") else {}
            }
        except AdapterError as e:
            msg = f"Error from text extractor '{self.x2text.x2text_instance.get_name()}'. "
            msg += str(e)
            logger.error(msg)
            return {"error": msg, "code": e.status_code if hasattr(e, 'status_code') else 500}
