import base64
import io
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from PIL import Image
from unstract.sdk1.adapters.exceptions import AdapterError
from unstract.sdk1.adapters.x2text import adapters
from unstract.sdk1.adapters.x2text.minicpm_ocr.src import MiniCPMOCR

Server = tuple[str, list, list]


@pytest.fixture
def server() -> Iterator[Server]:
    requests = []
    responses = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.path, self.headers.get("Authorization"), data))
            status, body = (
                responses.pop(0)
                if responses
                else (
                    200,
                    {
                        "choices": [
                            {
                                "message": {"content": f"page {len(requests)}"},
                                "finish_reason": "stop",
                            }
                        ]
                    },
                )
            )
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            requests.append((self.path, self.headers.get("Authorization"), None))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args: object) -> None:
            pass

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}", requests, responses
    httpd.shutdown()
    thread.join()
    httpd.server_close()


class MemoryStorage:
    def __init__(self, data: bytes) -> None:
        """Keep input and capture output in memory."""
        self.data = data
        self.writes = []

    def read(self, **kwargs: object) -> bytes:
        return self.data

    def write(self, **kwargs: object) -> None:
        self.writes.append(kwargs)


def image_bytes(fmt: str = "PNG", pages: int = 1) -> bytes:
    image = Image.new("RGB", (32, 24), "white")
    output = io.BytesIO()
    if fmt == "PDF":
        image.save(output, format=fmt, save_all=True, append_images=[image] * (pages - 1))
    else:
        image.save(output, format=fmt)
    return output.getvalue()


def test_registration_and_image_request(server: Server) -> None:
    url, requests, _ = server
    assert MiniCPMOCR.get_id() in adapters
    adapter = MiniCPMOCR(
        {"base_url": url + "/v1?foo=bar", "api_key": "secret", "max_tokens": 1024}
    )
    fs = MemoryStorage(image_bytes())
    result = adapter.process("input.png", "output.txt", fs=fs)
    assert result.extracted_text == "page 1"
    assert result.page_count == 1
    assert fs.writes[0]["data"] == "page 1"
    path, auth, body = requests[0]
    assert path == "/v1/chat/completions?foo=bar"
    assert auth == "Bearer secret"
    assert body["model"] == "minicpm-ocr"
    assert body["max_tokens"] == 1024
    assert body["temperature"] == 0.01 and body["top_p"] == 0.001
    assert body["top_k"] == 1 and body["no_repeat_ngram_size"] == 100
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    content = body["messages"][0]["content"]
    assert content[1]["text"] == "Text Recognition:"
    assert base64.b64decode(content[0]["image_url"]["url"].split(",")[1]).startswith(
        b"\x89PNG"
    )


def test_pdf_pages_and_openai_dialect(server: Server) -> None:
    url, requests, _ = server
    adapter = MiniCPMOCR({"base_url": url, "backend": "openai"})
    result = adapter.process("input.pdf", fs=MemoryStorage(image_bytes("PDF", pages=2)))
    assert result.extracted_text == "page 1\fpage 2"
    assert result.page_count == 2
    assert len(requests) == 2
    assert requests[0][1] is None
    assert "top_k" not in requests[0][2]


def test_failure_does_not_write_partial_output(server: Server) -> None:
    url, _, responses = server
    responses.extend([(200, {"choices": [{"message": {"content": "first"}}]}), (500, {})])
    fs = MemoryStorage(image_bytes("PDF", pages=2))
    with pytest.raises(AdapterError):
        MiniCPMOCR({"base_url": url}).process("file.pdf", "out.txt", fs=fs)
    assert fs.writes == []


@pytest.mark.parametrize(
    "body",
    [
        {"choices": []},
        {"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]},
        {"choices": [{"message": {"content": None, "refusal": "no"}}]},
    ],
)
def test_invalid_response(server: Server, body: dict) -> None:
    url, _, responses = server
    responses.append((200, body))
    with pytest.raises(AdapterError):
        MiniCPMOCR({"base_url": url}).process("image", fs=MemoryStorage(image_bytes()))


def test_invalid_image_and_url(server: Server) -> None:
    url, requests, _ = server
    with pytest.raises(AdapterError):
        MiniCPMOCR({"base_url": url}).process("image", fs=MemoryStorage(b"not an image"))
    with pytest.raises(AdapterError):
        MiniCPMOCR({"base_url": "http://user:password@example.com"}).process(
            "image", fs=MemoryStorage(image_bytes())
        )
    assert not requests


def test_connection(server: Server) -> None:
    url, requests, _ = server
    adapter = MiniCPMOCR({"base_url": url + "/v1/chat/completions", "api_key": "key"})
    assert adapter.test_connection()
    assert requests[0][:2] == ("/v1/models", "Bearer key")


def test_local_file_storage(server: Server, tmp_path: Path) -> None:
    url, _, _ = server
    source = tmp_path / "input.png"
    output = tmp_path / "output.txt"
    source.write_bytes(image_bytes())
    result = MiniCPMOCR({"base_url": url}).process(str(source), str(output))
    assert result.extracted_text == "page 1"
    assert output.read_text() == "page 1"


def test_http_failure_hides_query_credentials(server: Server) -> None:
    import traceback

    url, _, responses = server
    responses.append((403, {}))
    token = "secret" + "-value"
    with pytest.raises(AdapterError) as exc:
        MiniCPMOCR({"base_url": url + "?token=" + token}).process(
            "image", fs=MemoryStorage(image_bytes())
        )
    assert token not in "".join(traceback.format_exception(exc.value))


@pytest.mark.parametrize("mode", ["RGBA", "P"])
def test_transparency_is_composited_on_white(server: Server, mode: str) -> None:
    url, requests, _ = server
    image = Image.new("RGBA", (2, 1), (0, 0, 0, 0))
    image.putpixel((1, 0), (0, 0, 0, 255))
    if mode == "P":
        image = image.convert("P", palette=Image.Palette.ADAPTIVE)
    data = io.BytesIO()
    image.save(data, format="PNG")
    MiniCPMOCR({"base_url": url}).process(
        "transparent.png", fs=MemoryStorage(data.getvalue())
    )
    body = requests[0][2]
    encoded = body["messages"][0]["content"][0]["image_url"]["url"].split(",")[1]
    with Image.open(io.BytesIO(base64.b64decode(encoded))) as actual:
        assert actual.convert("RGB").getpixel((0, 0)) == (255, 255, 255)
        assert actual.convert("RGB").getpixel((1, 0)) == (0, 0, 0)
