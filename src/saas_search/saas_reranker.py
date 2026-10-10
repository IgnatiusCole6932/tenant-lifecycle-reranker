"""Domain policy for tenant-aware B2B SaaS search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class RerankGateway(Protocol):
    def rerank(
        self,
        query: str,
        candidates: list[str],
        top_k: int,
        *,
        model: str = "auto",
        vendor: str = "auto",
    ) -> dict[str, Any]:
        return {}


@dataclass(frozen=True, slots=True)
class TenantContext:
    onboarding_stage: str
    account_status: str
    actor_role: str


@dataclass(frozen=True, slots=True)
class SearchCandidate:
    id: str
    title: str
    summary: str


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    id: str
    title: str
    summary: str
    relevance_score: float


class TenantSearchReranker:
    def __init__(self, gateway: RerankGateway) -> None:
        self.gateway = gateway

    def rank(
        self,
        query: str,
        tenant: TenantContext,
        candidates: list[SearchCandidate],
        top_k: int,
    ) -> list[RankedCandidate]:
        if not candidates:
            return []

        contextual_query = (
            f"{query}\nTenant context: onboarding={tenant.onboarding_stage}; "
            f"account={tenant.account_status}; actor={tenant.actor_role}. "
            "Prefer results whose operation is valid for this lifecycle state and role."
        )
        documents = [f"{item.title}\n{item.summary}" for item in candidates]
        envelope = self.gateway.rerank(
            contextual_query,
            documents,
            min(top_k, len(candidates)),
            model="auto",
            vendor="auto",
        )
        rows = self._result_rows(envelope["data"])
        return [
            RankedCandidate(
                id=candidates[index].id,
                title=candidates[index].title,
                summary=candidates[index].summary,
                relevance_score=score,
            )
            for index, score in rows
        ]

    @staticmethod
    def _result_rows(data: Any) -> list[tuple[int, float]]:
        raw_rows = data.get("results", data) if isinstance(data, dict) else data
        if not isinstance(raw_rows, list):
            raise ValueError("Rerank data must contain a result list")
        return [
            (int(row["index"]), float(row.get("relevance_score", row.get("score", 0.0))))
            for row in raw_rows
        ]
