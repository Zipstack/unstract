import logging
from io import BytesIO
from typing import Any

import requests
from account.models import PlatformKey
from django.conf import settings
from platform_settings.platform_auth_service import PlatformAuthenticationService

logger = logging.getLogger(__name__)


class MultiDocService:

    def __init__(self, org_id: str, email: str) -> None:

        platform_key: PlatformKey = (
            PlatformAuthenticationService.get_active_platform_key(org_id)
        )
        self.headers: dict[str, str] = {"Authorization": f"Bearer {platform_key.key}"}

        self.url = f"{settings.MULTI_DOC_CHAT_SERVICE_URL}"
        self.email: str = email

    def upload_file(
        self, file_name: str, file_content: BytesIO, tag: str, email: str
    ) -> Any:

        payload = {
            "email": self.email,
            "tags": tag,
            "chunk_size": "0",
            "chunk_overlap": "0",
        }
        files = [("files", (file_name, file_content, "application/pdf"))]

        response: requests.Response = requests.request(
            "POST",
            f"{self.url}/md/file/upload",
            headers=self.headers,
            data=payload,
            files=files,
        )

        logger.info("File uploaded to multi doc chat api %s", file_name)

        return response.json()

    def search(self, tag: str) -> Any:

        payload: dict[str, str] = {"email": self.email, "tags": tag}

        response: requests.Response = requests.request(
            "POST",
            f"{self.url}/md/file/search",
            headers=self.headers,
            data=payload,
        )

        return response.json()

    def chat(self, question: str, tag: str) -> Any:

        payload = {
            "email": self.email,
            "search_tags": tag,
            "question": question,
        }

        response: requests.Response = requests.request(
            "POST",
            f"{self.url}/md/chat",
            headers=self.headers,
            data=payload,
        )

        return response.json()
