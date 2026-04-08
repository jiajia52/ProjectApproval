"""OpenAI SDK based chat client for approval reasoning."""

from __future__ import annotations

import json
import os
from typing import Any

from openai import BadRequestError, DefaultHttpxClient, OpenAI

from app.core.config import env as _env  # noqa: F401


class LLMConfigError(RuntimeError):
    """Raised when the local LLM configuration is incomplete."""


def load_llm_settings() -> dict[str, Any]:
    base_url = os.getenv("PROJECT_APPROVAL_LLM_BASE_URL", "").strip()
    api_key = os.getenv("PROJECT_APPROVAL_LLM_API_KEY", "").strip()
    model = os.getenv("PROJECT_APPROVAL_LLM_MODEL", "").strip()
    timeout = float(os.getenv("PROJECT_APPROVAL_LLM_TIMEOUT", "180") or 180)
    verify_ssl = os.getenv("PROJECT_APPROVAL_LLM_VERIFY_SSL", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if not base_url or not api_key or not model:
        raise LLMConfigError(
            "缺少 LLM 配置，请在 .env 中设置 PROJECT_APPROVAL_LLM_BASE_URL、"
            "PROJECT_APPROVAL_LLM_API_KEY 和 PROJECT_APPROVAL_LLM_MODEL。"
        )
    return {
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
        "model": model,
        "timeout": timeout,
        "verify_ssl": verify_ssl,
    }


def extract_json(text: str) -> Any:
    content = text.strip()
    if content.startswith("```"):
        chunks = [chunk.strip() for chunk in content.split("```") if chunk.strip()]
        for chunk in chunks:
            candidate = chunk[4:].strip() if chunk.lower().startswith("json") else chunk
            try:
                return json.loads(candidate)
            except Exception:
                continue
    return json.loads(content)


def _build_client(settings: dict[str, Any]) -> OpenAI:
    return OpenAI(
        api_key=settings["api_key"],
        base_url=settings["base_url"],
        timeout=settings["timeout"],
        max_retries=0,
        http_client=DefaultHttpxClient(
            verify=settings["verify_ssl"],
            trust_env=False,
        ),
    )


def _create_chat_completion(
    client: OpenAI,
    settings: dict[str, Any],
    messages: list[dict[str, str]],
    *,
    temperature: float,
    use_response_format: bool,
):
    payload: dict[str, Any] = {
        "model": settings["model"],
        "messages": messages,
        "temperature": temperature,
    }
    if use_response_format:
        payload["response_format"] = {"type": "json_object"}
    return client.chat.completions.create(**payload)


def chat_json(messages: list[dict[str, str]], *, temperature: float = 0.1) -> dict[str, Any]:
    settings = load_llm_settings()
    client = _build_client(settings)
    used_response_format = True
    try:
        response = _create_chat_completion(
            client,
            settings,
            messages,
            temperature=temperature,
            use_response_format=True,
        )
    except BadRequestError as exc:
        error_text = str(exc).lower()
        if "response_format" not in error_text and "json_object" not in error_text:
            raise
        used_response_format = False
        response = _create_chat_completion(
            client,
            settings,
            messages,
            temperature=temperature,
            use_response_format=False,
        )

    payload = response.model_dump()
    content = response.choices[0].message.content or ""
    return {
        "raw": payload,
        "content": content,
        "json": extract_json(content),
        "used_response_format": used_response_format,
    }
