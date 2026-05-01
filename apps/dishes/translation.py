import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings


logger = logging.getLogger(__name__)

MAX_TRANSLATE_ITEMS = 50
MAX_TRANSLATE_BODY_BYTES = 128 * 1024
MAX_TRANSLATE_CHARS = 50_000
PLACEHOLDER_KEYS = {
    "",
    "YOU_API_TOKEN",
    "YOUR_API_TOKEN",
    "YOUR_AZURE_TRANSLATOR_KEY",
    "CHANGE-ME",
    "CHANGE_ME",
}


class TranslationError(Exception):
    code = "translation_error"


class TranslationNotConfigured(TranslationError):
    code = "not_configured"


class TranslationTimeout(TranslationError):
    code = "timeout"


class TranslationBadResponse(TranslationError):
    code = "bad_response"


class TranslationProviderError(TranslationError):
    code = "provider_error"

    def __init__(self, message: str = "", *, provider_status: int | None = None):
        super().__init__(message)
        self.provider_status = provider_status


def _auth_key() -> str:
    return str(getattr(settings, "AZURE_TRANSLATOR_KEY", "") or "").strip()


def is_translation_configured() -> bool:
    return _auth_key().upper() not in PLACEHOLDER_KEYS


def translate_ru_to_en(texts: list[str]) -> list[str]:
    cleaned = [str(text or "").strip() for text in texts]
    if not cleaned:
        return []
    if not is_translation_configured():
        raise TranslationNotConfigured("Azure Translator key is not configured")
    if len(cleaned) > MAX_TRANSLATE_ITEMS:
        raise TranslationBadResponse(f"too many texts: {len(cleaned)}")
    if sum(len(text) for text in cleaned) > MAX_TRANSLATE_CHARS:
        raise TranslationBadResponse("request text is too large")

    logger.info("azure translation start: items=%s", len(cleaned))
    translations = _translate_with_azure(cleaned)
    logger.info("azure translation done: items=%s", len(translations))
    return translations


def _translate_with_azure(texts: list[str]) -> list[str]:
    source_lang = getattr(settings, "AZURE_TRANSLATOR_SOURCE_LANG", "ru")
    target_lang = getattr(settings, "AZURE_TRANSLATOR_TARGET_LANG", "en")
    query = urllib.parse.urlencode(
        {
            "api-version": "3.0",
            "from": source_lang,
            "to": target_lang,
        }
    )
    body = json.dumps([{"Text": text} for text in texts], ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_TRANSLATE_BODY_BYTES:
        raise TranslationBadResponse("request body is too large")

    endpoint = getattr(
        settings,
        "AZURE_TRANSLATOR_ENDPOINT",
        "https://api.cognitive.microsofttranslator.com",
    ).rstrip("/")
    url = f"{endpoint}/translate?{query}"
    headers = {
        "Ocp-Apim-Subscription-Key": _auth_key(),
        "Content-Type": "application/json; charset=utf-8",
        "Accept": "application/json",
    }
    region = str(getattr(settings, "AZURE_TRANSLATOR_REGION", "") or "").strip()
    if region:
        headers["Ocp-Apim-Subscription-Region"] = region

    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        timeout = getattr(settings, "AZURE_TRANSLATOR_TIMEOUT_SECONDS", 10)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read(MAX_TRANSLATE_BODY_BYTES).decode("utf-8")
    except TimeoutError as exc:
        logger.warning("azure translation timeout")
        raise TranslationTimeout("Azure Translator request timed out") from exc
    except socket.timeout as exc:
        logger.warning("azure translation socket timeout")
        raise TranslationTimeout("Azure Translator request timed out") from exc
    except urllib.error.HTTPError as exc:
        logger.warning("azure translation http error: status=%s", exc.code)
        raise TranslationProviderError(f"Azure Translator HTTP error: {exc.code}", provider_status=exc.code) from exc
    except urllib.error.URLError as exc:
        logger.warning("azure translation url error: reason=%s", exc.reason)
        raise TranslationProviderError("Azure Translator request failed") from exc

    try:
        data = json.loads(payload)
        result = [
            str(item["translations"][0].get("text", "")).strip()
            for item in data
        ]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("azure translation bad response")
        raise TranslationBadResponse("Azure Translator response format is invalid") from exc

    if len(result) != len(texts) or any(not item for item in result):
        logger.warning(
            "azure translation incomplete response: expected=%s actual=%s",
            len(texts),
            len(result),
        )
        raise TranslationBadResponse("Azure Translator response is incomplete")
    return result
