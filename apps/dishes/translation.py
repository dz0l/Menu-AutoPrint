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
PLACEHOLDER_KEYS = {"", "YOU_API_TOKEN", "YOUR_API_TOKEN", "CHANGE-ME", "CHANGE_ME"}


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
    return str(getattr(settings, "DEEPL_AUTH_KEY", "") or "").strip()


def is_translation_configured() -> bool:
    return _auth_key().upper() not in PLACEHOLDER_KEYS


def translate_ru_to_en(texts: list[str]) -> list[str]:
    cleaned = [str(text or "").strip() for text in texts]
    if not cleaned:
        return []
    if not is_translation_configured():
        raise TranslationNotConfigured("DeepL API key is not configured")
    if len(cleaned) > MAX_TRANSLATE_ITEMS:
        raise TranslationBadResponse(f"too many texts: {len(cleaned)}")

    logger.info("deepl translation start: items=%s", len(cleaned))
    translations = _translate_with_deepl(cleaned)
    logger.info("deepl translation done: items=%s", len(translations))
    return translations


def _translate_with_deepl(texts: list[str]) -> list[str]:
    fields: list[tuple[str, str]] = [
        ("source_lang", getattr(settings, "DEEPL_SOURCE_LANG", "RU")),
        ("target_lang", getattr(settings, "DEEPL_TARGET_LANG", "EN")),
    ]
    fields.extend(("text", text) for text in texts)
    body = urllib.parse.urlencode(fields).encode("utf-8")
    if len(body) > MAX_TRANSLATE_BODY_BYTES:
        raise TranslationBadResponse("request body is too large")

    url = f"{getattr(settings, 'DEEPL_API_URL', 'https://api-free.deepl.com').rstrip('/')}/v2/translate"
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"DeepL-Auth-Key {_auth_key()}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=getattr(settings, "DEEPL_TIMEOUT_SECONDS", 10)) as response:
            payload = response.read(MAX_TRANSLATE_BODY_BYTES).decode("utf-8")
    except TimeoutError as exc:
        logger.warning("deepl translation timeout")
        raise TranslationTimeout("DeepL request timed out") from exc
    except socket.timeout as exc:
        logger.warning("deepl translation socket timeout")
        raise TranslationTimeout("DeepL request timed out") from exc
    except urllib.error.HTTPError as exc:
        logger.warning("deepl translation http error: status=%s", exc.code)
        raise TranslationProviderError(f"DeepL HTTP error: {exc.code}", provider_status=exc.code) from exc
    except urllib.error.URLError as exc:
        logger.warning("deepl translation url error: reason=%s", exc.reason)
        raise TranslationProviderError("DeepL request failed") from exc

    try:
        data = json.loads(payload)
        translations = data["translations"]
        result = [str(item.get("text", "")).strip() for item in translations]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("deepl translation bad response")
        raise TranslationBadResponse("DeepL response format is invalid") from exc

    if len(result) != len(texts) or any(not item for item in result):
        logger.warning("deepl translation incomplete response: expected=%s actual=%s", len(texts), len(result))
        raise TranslationBadResponse("DeepL response is incomplete")
    return result
