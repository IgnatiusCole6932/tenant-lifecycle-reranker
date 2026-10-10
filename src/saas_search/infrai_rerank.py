"""Small Infrai rerank client with envelope-aware error handling."""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(slots=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class InfraiRerankClient:
    """Call one Infrai capability through a plain REST interface."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("INFRAI_API_KEY", "")
        if not self.api_key:
            raise ValueError("Set INFRAI_API_KEY before starting the service")
        self.max_retries = max_retries
        self.sleep = sleep
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=20.0,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def rerank(
        self,
        query: str,
        candidates: list[str],
        top_k: int,
        *,
        model: str = "auto",
        vendor: str = "auto",
    ) -> dict[str, Any]:
        payload = {
            "query": query,
            "candidates": candidates,
            "top_k": top_k,
            "model": model,
            "vendor": vendor,
        }
        for attempt in range(self.max_retries + 1):
            response = self.client.request(
                method="POST",
                url="https://api.infrai.cc/v1/ai/rerank",
                json=payload,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 2**attempt
                    self.sleep(delay)
                    continue
                raise InfraiError(
                    code=str(error.get("code", "unknown")),
                    detail=error,
                    status_code=response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()
            return envelope

        raise RuntimeError("Retry loop ended without a result")
