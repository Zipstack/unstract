"""MiniCPM-OCR text extraction via an OpenAI-compatible endpoint."""

import base64
import io
import os
from contextlib import closing
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
import pypdfium2 as pdfium
from PIL import Image, UnidentifiedImageError
from unstract.sdk1.adapters.exceptions import AdapterError
from unstract.sdk1.adapters.x2text.dto import TextExtractionResult
from unstract.sdk1.adapters.x2text.x2text_adapter import X2TextAdapter
from unstract.sdk1.file_storage import FileStorage, FileStorageProvider

_MAX_PAGES = 300
_MAX_PAGE_PIXELS = 16_000_000


class MiniCPMOCR(X2TextAdapter):
    """Extract page text from images or PDFs using a hosted MiniCPM-OCR model."""

    SCHEMA_PATH = f"{os.path.dirname(__file__)}/static/json_schema.json"

    def __init__(self, settings: dict[str, Any]) -> None:
        """Initialize the adapter with its connection settings."""
        super().__init__("MiniCPMOCR")
        self.config = settings

    @staticmethod
    def get_id() -> str:
        return "minicpmocr|2d36b13e-1444-4404-9d0e-f388ae890091"

    @staticmethod
    def get_name() -> str:
        return "MiniCPM-OCR"

    @staticmethod
    def get_description() -> str:
        return "Self-hosted MiniCPM-OCR text extractor"

    @staticmethod
    def get_icon() -> str:
        return "/icons/adapter-icons/MiniCPMOCR.svg"

    def _endpoint(self, suffix: str) -> str:
        raw = str(self.config.get("base_url") or "").strip()
        try:
            url = urlsplit(raw)
            if url.scheme not in ("http", "https") or not url.hostname or url.username:
                raise ValueError
            path = url.path.rstrip("/")
            if path.endswith("/chat/completions"):
                path = path[: -len("/chat/completions")]
            if not path.endswith("/v1"):
                path += "/v1"
            return urlunsplit((url.scheme, url.netloc, path + suffix, url.query, ""))
        except ValueError as exc:
            raise AdapterError(
                "MiniCPM-OCR base URL must be an HTTP(S) URL without userinfo"
            ) from exc

    def _headers(self) -> dict[str, str]:
        key = str(self.config.get("api_key") or "").strip()
        return {"Authorization": f"Bearer {key}"} if key else {}

    def _request(self, image: bytes) -> str:
        model = str(self.config.get("model") or "minicpm-ocr").strip()
        body: dict[str, Any] = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": "data:image/png;base64,"
                                + base64.b64encode(image).decode("ascii")
                            },
                        },
                        {"type": "text", "text": "Text Recognition:"},
                    ],
                }
            ],
            "max_tokens": int(self.config.get("max_tokens") or 8192),
            "temperature": 0.01,
            "top_p": 0.001,
            "stream": False,
        }
        if self.config.get("backend", "vllm") == "vllm":
            body.update(
                {
                    "top_k": 1,
                    "repetition_penalty": 1.0,
                    "no_repeat_ngram_size": 100,
                    "chat_template_kwargs": {"enable_thinking": False},
                }
            )
        try:
            response = httpx.post(
                self._endpoint("/chat/completions"),
                json=body,
                headers=self._headers(),
                timeout=float(self.config.get("timeout") or 300),
                follow_redirects=False,
            )
            response.raise_for_status()
            choice = response.json()["choices"][0]
            if choice.get("finish_reason") == "length":
                raise AdapterError(
                    "MiniCPM-OCR output was truncated; increase max_tokens"
                )
            message = choice["message"]
            text = message.get("content")
            if message.get("refusal") or not isinstance(text, str):
                raise AdapterError(
                    "MiniCPM-OCR returned a refusal or unsupported response"
                )
            return text.strip()
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
            raise AdapterError(
                "MiniCPM-OCR request failed or returned an invalid response"
            ) from None

    def process(
        self,
        input_file_path: str,
        output_file_path: str | None = None,
        fs: FileStorage | None = None,
        **kwargs: dict[Any, Any],
    ) -> TextExtractionResult:
        if fs is None:
            fs = FileStorage(provider=FileStorageProvider.LOCAL)
        data = fs.read(path=input_file_path, mode="rb")
        if not isinstance(data, bytes) or not data:
            raise AdapterError("MiniCPM-OCR input is empty or unreadable")
        pages = (
            self._pdf_pages(data)
            if data.startswith(b"%PDF-")
            else [self._image_page(data)]
        )
        text = "\f".join(pages)
        if output_file_path:
            fs.write(path=output_file_path, mode="w", data=text, encoding="utf-8")
        return TextExtractionResult(extracted_text=text, page_count=len(pages))

    def _pdf_pages(self, data: bytes) -> list[str]:
        pages = []
        try:
            with closing(pdfium.PdfDocument(data)) as doc:
                if not 0 < len(doc) <= _MAX_PAGES:
                    raise AdapterError(f"PDF must contain 1 to {_MAX_PAGES} pages")
                for page in doc:
                    with closing(page):
                        width, height = page.get_size()
                        if (
                            width <= 0
                            or height <= 0
                            or width * height * (150 / 72) ** 2 > _MAX_PAGE_PIXELS
                        ):
                            raise AdapterError(
                                "PDF page exceeds the rendering size limit"
                            )
                        bitmap = page.render(scale=150 / 72)
                        try:
                            buffer = io.BytesIO()
                            bitmap.to_pil().save(buffer, format="PNG")
                            pages.append(self._request(buffer.getvalue()))
                        finally:
                            bitmap.close()
        except pdfium.PdfiumError as exc:
            raise AdapterError("Unable to render input PDF") from exc
        return pages

    def _image_page(self, data: bytes) -> str:
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.width * image.height > _MAX_PAGE_PIXELS:
                    raise AdapterError("Image exceeds the size limit")
                if image.format not in {"PNG", "JPEG", "WEBP"}:
                    raise AdapterError(
                        "Supported input formats are PDF, PNG, JPEG and WebP"
                    )
                buffer = io.BytesIO()
                rgba = image.convert("RGBA")
                background = Image.new("RGB", rgba.size, "white")
                background.paste(rgba, mask=rgba.getchannel("A"))
                background.save(buffer, format="PNG")
                return self._request(buffer.getvalue())
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise AdapterError("Unable to read input image") from exc

    def test_connection(self) -> bool:
        try:
            response = httpx.get(
                self._endpoint("/models"),
                headers=self._headers(),
                timeout=float(self.config.get("timeout") or 300),
                follow_redirects=False,
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError:
            raise AdapterError(
                "Unable to reach the MiniCPM-OCR models endpoint"
            ) from None
