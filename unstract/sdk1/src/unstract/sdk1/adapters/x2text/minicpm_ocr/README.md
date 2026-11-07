# MiniCPM-OCR text extractor

Configure the MiniCPM-OCR text extractor in Unstract with the root or `/v1` URL of a running OpenAI-compatible server, its served model name (default `minicpm-ocr`), and an optional API key. The connection test checks `GET /v1/models`; this endpoint must be enabled on the server.

PDFs are rendered locally at 150 DPI and each page is sent as a PNG with the `Text Recognition:` prompt. PNG, JPEG, and WebP images are also supported. Returned pages are separated by form feed. This is page-level recognition, not the MiniCPM SDK's full layout detection and crop pipeline; table structure and reading order are not guaranteed. Other document formats must be converted to PDF or image before extraction. PDFs are limited to 300 pages and each image to 16 million pixels.

The `vllm` dialect sends the official vLLM sampling settings, including `top_k`, repetition penalty, no-repeat n-grams and disabled thinking. Select `openai` for servers accepting only standard OpenAI chat parameters; support and exact decoding behavior vary by serving engine. Adjust the per-page timeout and token budget for long or dense pages. A length-limited output fails rather than silently saving incomplete text.

Document page images are sent to the configured endpoint. Use a trusted service and secure transport appropriate to the deployment.
