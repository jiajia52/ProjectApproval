from __future__ import annotations

from fastapi import HTTPException
from openai import APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError

from app.approvals.clients.iwork_client import RemoteAPIError


def to_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RemoteAPIError):
        return HTTPException(status_code=502, detail=f"远程接口返回错误[{exc.code}]: {exc.message}")
    return HTTPException(status_code=502, detail=str(exc))


def is_llm_unavailable_error(exc: Exception) -> bool:
    return isinstance(exc, (APIConnectionError, APITimeoutError, AuthenticationError, RateLimitError))
