"""Provider-independent model calls.

Supported chat providers: offline, ollama (local), meta, openai_compatible.
Keys are read from the environment. Loopback HTTP is allowed for Ollama only.
Redirects are not followed. Secrets are stripped from errors.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import urlsplit

from .config_loader import Config, env_secret
from .results import ModelResult

Transport = Callable[[str, dict, dict, float, bool], tuple[int, Any]]


class ProviderError(RuntimeError):
    def __init__(self, message: str):
        super().__init__(message)


def redact(text: str, secret: str) -> str:
    if not secret or not text:
        return text
    return text.replace(secret, "[redacted]")


def _loopback(hostname: str | None) -> bool:
    return hostname in {"127.0.0.1", "localhost", "::1"}


def validate_url(url: str, *, allow_loopback_http: bool) -> None:
    parts = urlsplit(url)
    if parts.username or parts.password or parts.fragment:
        raise ProviderError("Model URL must not contain credentials or a fragment.")
    if not parts.hostname:
        raise ProviderError("Model URL is missing a host.")
    if parts.scheme == "https":
        return
    if parts.scheme == "http" and allow_loopback_http and _loopback(parts.hostname):
        return
    raise ProviderError("Model URL must be HTTPS, or HTTP only on localhost.")


def urllib_transport(url: str, payload: dict, headers: dict, timeout: float,
                     allow_loopback_http: bool) -> tuple[int, Any]:
    validate_url(url, allow_loopback_http=allow_loopback_http)
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(1_000_001)
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        body = exc.read(4000).decode("utf-8", errors="replace")
        return exc.code, body
    except urllib.error.URLError as exc:
        raise ProviderError(f"Could not reach the model provider: {exc.reason}") from None
    except TimeoutError as exc:
        raise ProviderError("The model provider timed out.") from exc
    if len(raw) > 1_000_000:
        raise ProviderError("The model response was too large.")
    text = raw.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text)
    except json.JSONDecodeError:
        return status, text


def _clip_error(value: Any, secret: str) -> str:
    if isinstance(value, dict):
        err = value.get("error")
        if isinstance(err, dict):
            value = err.get("message") or err
        elif isinstance(err, str):
            value = err
        else:
            value = json.dumps(value)[:300]
    text = str(value).replace("\n", " ")[:300]
    return redact(text, secret)


def _openai_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts).strip()
    return ""


def _ollama_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    message = payload.get("message")
    if isinstance(message, dict) and isinstance(message.get("content"), str):
        return message["content"].strip()
    if isinstance(payload.get("response"), str):
        return payload["response"].strip()
    return ""


def chat(config: Config, messages: list[dict], *, transport: Transport | None = None,
         timeout: float = 20.0) -> ModelResult:
    provider = str(config.get("provider") or "offline").strip().lower()
    poster = transport or urllib_transport
    if provider == "offline":
        return ModelResult("", "offline", error="offline")
    if provider == "ollama":
        return _ollama_chat(config, messages, poster, timeout)
    if provider == "meta":
        return _openai_chat(config, "meta", messages, poster, timeout)
    if provider in {"openai_compatible", "openai"}:
        return _openai_chat(config, "openai_compatible", messages, poster, timeout)
    return ModelResult("", provider, error=f"Unknown provider '{provider}'.")


def _ollama_chat(config: Config, messages: list[dict], transport: Transport, timeout: float) -> ModelResult:
    base = str(config.get("ollama", "base_url") or "http://127.0.0.1:11434").rstrip("/")
    model = str(config.get("ollama", "model") or "").strip()
    if not model:
        return ModelResult("", "ollama", error="Ollama model is empty in config.")
    url = base + "/api/chat"
    payload = {"model": model, "messages": messages, "stream": False}
    try:
        status, body = transport(url, payload, {"Content-Type": "application/json"}, timeout, True)
    except ProviderError as exc:
        return ModelResult("", "ollama", error=str(exc), model=model)
    if status != 200:
        return ModelResult("", "ollama", error=f"Ollama returned HTTP {status}: {_clip_error(body, '')}", model=model)
    text = _ollama_text(body)
    if not text:
        return ModelResult("", "ollama", error="Ollama returned no text.", model=model)
    return ModelResult(text[:600], "ollama", model=model)


def _openai_chat(config: Config, section: str, messages: list[dict], transport: Transport,
                 timeout: float) -> ModelResult:
    base = str(config.get(section, "base_url") or "").rstrip("/")
    model = str(config.get(section, "model") or "").strip()
    key_env = str(config.get(section, "api_key_env") or "")
    secret = env_secret(key_env)
    # Legacy env names still work for the compatible provider.
    if not secret and section == "openai_compatible":
        secret = env_secret("BUDDY_CHAT_API_KEY")
    if not model and section == "openai_compatible":
        import os
        model = os.environ.get("BUDDY_CHAT_MODEL", "").strip()
    if not base and section == "openai_compatible":
        import os
        base = os.environ.get("BUDDY_CHAT_URL", "").strip().rstrip("/")
        if base.endswith("/chat/completions"):
            base = base[: -len("/chat/completions")]
    if not base or not model:
        return ModelResult("", section, error=f"{section} base URL or model is empty.")
    if not secret:
        return ModelResult("", section, error=f"Set the API key in environment variable {key_env or 'BUDDY_CHAT_API_KEY'}.")
    url = base + "/chat/completions"
    payload = {"model": model, "messages": messages, "max_tokens": 120, "temperature": 0.8}
    headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
    try:
        status, body = transport(url, payload, headers, timeout, False)
    except ProviderError as exc:
        return ModelResult("", section, error=redact(str(exc), secret), model=model)
    if status != 200:
        return ModelResult("", section, error=f"Provider returned HTTP {status}: {_clip_error(body, secret)}", model=model)
    text = redact(_openai_text(body), secret)
    if not text:
        return ModelResult("", section, error="Provider returned no text.", model=model)
    return ModelResult(text[:600], section, model=model)


def vision_chat(config: Config, prompt: str, jpeg: bytes, *, transport: Transport | None = None,
                timeout: float = 25.0) -> ModelResult:
    """One vision call. provider comes from config vision.provider."""
    import base64
    section = config.get("vision") or {}
    provider = str(section.get("provider") or "none").lower()
    poster = transport or urllib_transport
    if provider in {"", "none", "off"}:
        return ModelResult("", "none", error="No vision provider is configured.")
    model = str(section.get("model") or "").strip()
    if not model:
        return ModelResult("", provider, error="Vision model is empty in config.")
    encoded = base64.b64encode(jpeg).decode("ascii")
    if provider == "ollama":
        base = str(section.get("base_url") or config.get("ollama", "base_url") or "http://127.0.0.1:11434").rstrip("/")
        url = base + "/api/chat"
        payload = {
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt, "images": [encoded]}],
        }
        try:
            status, body = poster(url, payload, {"Content-Type": "application/json"}, timeout, True)
        except ProviderError as exc:
            return ModelResult("", "ollama", error=str(exc), model=model)
        if status != 200:
            return ModelResult("", "ollama", error=f"Ollama vision returned HTTP {status}: {_clip_error(body, '')}", model=model)
        text = _ollama_text(body)
        if not text:
            return ModelResult("", "ollama", error="Ollama vision returned no text.", model=model)
        return ModelResult(text[:1500], "ollama", model=model)

    key_env = str(section.get("api_key_env") or "BUDDY_VISION_API_KEY")
    secret = env_secret(key_env) or env_secret("BUDDY_VISION_API_KEY")
    base = str(section.get("base_url") or "").rstrip("/")
    if not base and provider == "meta":
        base = str(config.get("meta", "base_url") or "").rstrip("/")
    if not secret:
        return ModelResult("", provider, error=f"Set the vision API key in {key_env}.")
    if not base:
        return ModelResult("", provider, error="Vision base URL is empty.")
    url = base + "/chat/completions"
    payload = {
        "model": model,
        "max_tokens": 220,
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{encoded}", "detail": "low"}},
            ]},
        ],
    }
    headers = {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
    try:
        status, body = poster(url, payload, headers, timeout, False)
    except ProviderError as exc:
        return ModelResult("", provider, error=redact(str(exc), secret), model=model)
    if status != 200:
        return ModelResult("", provider, error=f"Vision provider returned HTTP {status}: {_clip_error(body, secret)}", model=model)
    text = redact(_openai_text(body), secret)
    if not text:
        return ModelResult("", provider, error="Vision provider returned no text.", model=model)
    return ModelResult(text[:1500], provider, model=model)
