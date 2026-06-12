class LlamaParseConfig:
    """Dictionary keys used to process LlamaParse."""

    API_KEY = "api_key"
    BASE_URL = "base_url"
    # Legacy schema key for the base URL, kept for backward compatibility with
    # adapter instances saved before the rename (#1972).
    LEGACY_BASE_URL = "url"
    RESULT_TYPE = "result_type"
    NUM_WORKERS = "num_workers"
    VERBOSE = "verbose"
    LANGUAGE = "language"
