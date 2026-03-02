"""Mock implementations of LLM and Storage clients for testing.

These are temporary implementations for testing the API layer
before integrating with real services in Phase 4.
"""

import json
import random
import time
from typing import Any


class MockLLMClient:
    """Mock LLM client for testing Look-Up execution.

    Generates synthetic responses for testing purposes.
    """

    def generate(self, prompt: str, config: dict[str, Any], timeout: int = 30) -> str:
        """Generate a mock LLM response.

        Returns JSON-formatted enrichment data with random confidence.
        """
        # Simulate processing time
        time.sleep(random.uniform(0.1, 0.5))

        # Extract vendor name from prompt if available
        vendor = "Unknown"
        if "vendor" in prompt.lower():
            # Try to extract vendor name from prompt
            lines = prompt.split("\n")
            for line in lines:
                if "vendor" in line.lower() and ":" in line:
                    vendor = line.split(":")[-1].strip()
                    break

        # Generate mock enrichment data
        confidence = random.uniform(0.6, 0.98)
        enrichment_data = {
            "canonical_vendor": self._canonicalize(vendor),
            "vendor_category": random.choice(
                ["SaaS", "Infrastructure", "Security", "Analytics"]
            ),
            "vendor_type": random.choice(["Software", "Service", "Platform"]),
            "confidence": round(confidence, 2),
        }

        return json.dumps(enrichment_data)

    def _canonicalize(self, vendor: str) -> str:
        """Mock canonicalization of vendor names."""
        # Simple mock canonicalization
        mappings = {
            "Slack Technologies": "Slack",
            "Microsoft Corp": "Microsoft",
            "Amazon Web Services": "AWS",
            "Google Cloud Platform": "GCP",
            "International Business Machines": "IBM",
        }
        return mappings.get(vendor, vendor)


class MockStorageClient:
    """Mock storage client for testing reference data operations.

    Stores data in memory for testing purposes.
    """

    def __init__(self):
        """Initialize in-memory storage."""
        self.storage = {}

    def upload(self, path: str, content: bytes) -> bool:
        """Upload content to mock storage.

        Args:
            path: Storage path
            content: File content

        Returns:
            True if successful
        """
        self.storage[path] = content
        return True

    def download(self, path: str) -> bytes | None:
        """Download content from mock storage.

        Args:
            path: Storage path

        Returns:
            File content or None if not found
        """
        return self.storage.get(path)

    def delete(self, path: str) -> bool:
        """Delete content from mock storage.

        Args:
            path: Storage path

        Returns:
            True if deleted, False if not found
        """
        if path in self.storage:
            del self.storage[path]
            return True
        return False

    def exists(self, path: str) -> bool:
        """Check if path exists in storage.

        Args:
            path: Storage path

        Returns:
            True if exists
        """
        return path in self.storage

    def list_files(self, prefix: str) -> list:
        """List files with given prefix.

        Args:
            prefix: Path prefix

        Returns:
            List of matching paths
        """
        return [path for path in self.storage.keys() if path.startswith(prefix)]

    def get_text_content(self, path: str) -> str | None:
        """Get text content from storage.

        Args:
            path: Storage path

        Returns:
            Text content or None if not found
        """
        content = self.download(path)
        if content:
            return content.decode("utf-8")
        return None

    def get(self, path: str) -> str:
        """Retrieve file content from storage.

        This method implements the StorageClient protocol expected
        by ReferenceDataLoader.

        Args:
            path: Storage path

        Returns:
            Text content of the file

        Raises:
            FileNotFoundError: If file not found in storage
        """
        content = self.get_text_content(path)
        if content is None:
            raise FileNotFoundError(f"File not found: {path}")
        return content

    def save_text_content(self, path: str, text: str) -> bool:
        """Save text content to storage.

        Args:
            path: Storage path
            text: Text content

        Returns:
            True if successful
        """
        return self.upload(path, text.encode("utf-8"))
