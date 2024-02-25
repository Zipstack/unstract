class EnvKey:
    GOOGLE_SERVICE_ACCOUNT = "GOOGLE_SERVICE_ACCOUNT"


class GoogleTranslateKey:
    PROCESSOR = "Google Translate"
    CREDENTIAL_SCOPES = ["https://www.googleapis.com/auth/cloud-platform"]


class StaticData:
    LANGUAGE_CODES = {
        "english": "en",
        "chinese": "zh",
        "spanish": "es",
        "arabic": "ar",
        "portuguese": "pt",
        "russian": "ru",
        "japanese": "ja",
        "german": "de",
        "french": "fr",
        "korean": "ko",
        "turkish": "tr",
        "italian": "it",
        "polish": "pl",
        "dutch": "nl",
        "swedish": "sv",
        "indonesian": "id",
        "danish": "da",
        "norwegian": "no",
        "finnish": "fi",
        "greek": "el",
        "hebrew": "he",
        "hungarian": "hu",
        "czech": "cs",
        "thai": "th",
        "vietnamese": "vi",
        "hindi": "hi",
        "ukrainian": "uk",
        "malay": "ms",
        "malayalam": "ml",
        "romanian": "ro",
        "northern_sami": "se",
        "slovak": "sk",
        "bulgarian": "bg",
        "croatian": "hr",
        "serbian": "sr",
        "bengali": "bn",
        "tamil": "ta",
        "persian": "fa",
        "slovenian": "sl",
        "lithuanian": "lt",
        "latvian": "lv",
        "estonian": "et",
        "icelandic": "is",
        "georgian": "ka",
        "albanian": "sq",
        "tagalog": "tl",
        "mongolian": "mn",
        "azerbaijani": "az",
        "kazakh": "kk",
    }

    ALLOWED_PROCESSORS = [
        GoogleTranslateKey.PROCESSOR,
        "Microsoft Translate",
        "Amazon Translate",
        "IBM Watson Translate",
        "DeepL Translate",
        "Zipstack/Unstract translate",
    ]

    SUPPORTED_PROCESSORS = [GoogleTranslateKey.PROCESSOR]
