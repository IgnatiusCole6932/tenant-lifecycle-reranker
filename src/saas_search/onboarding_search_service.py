"""HTTP entry point for tenant-aware SaaS result reranking."""

from __future__ import annotations

from contextlib import asynccontextmanager
from enum import Enum
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, Field

from .infrai_rerank import InfraiError, InfraiRerankClient
from .saas_reranker import SearchCandidate, TenantContext, TenantSearchReranker


class OnboardingStage(str, Enum):
    invited = "invited"
    configuring = "configuring"
    completed = "completed"


class AccountStatus(str, Enum):
    trial = "trial"
    active = "active"
    suspended = "suspended"
    closed = "closed"


class ActorRole(str, Enum):
    member = "member"
    admin = "admin"
    owner = "owner"


class TenantInput(BaseModel):
    onboarding_stage: OnboardingStage
    account_status: AccountStatus
    actor_role: ActorRole


class CandidateInput(BaseModel):
    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)


class RerankRequest(BaseModel):
    query: str = Field(min_length=1)
    tenant: TenantInput
    candidates: list[CandidateInput] = Field(min_length=1, max_length=100)
    top_k: int = Field(default=5, ge=1, le=25)


class RankedResult(BaseModel):
    id: str
    title: str
    summary: str
    relevance_score: float


class RerankResponse(BaseModel):
    results: list[RankedResult]


@asynccontextmanager
async def lifespan(app: FastAPI):
    client = InfraiRerankClient()
    app.state.reranker = TenantSearchReranker(client)
    yield
    client.close()


app = FastAPI(title="Tenant lifecycle search reranker", lifespan=lifespan)


def get_reranker(request: Request) -> TenantSearchReranker:
    return request.app.state.reranker


@app.post("/rerank", response_model=RerankResponse)
def rerank_results(
    body: RerankRequest,
    reranker: Annotated[TenantSearchReranker, Depends(get_reranker)],
) -> RerankResponse:
    try:
        ranked = reranker.rank(
            query=body.query,
            tenant=TenantContext(
                onboarding_stage=body.tenant.onboarding_stage.value,
                account_status=body.tenant.account_status.value,
                actor_role=body.tenant.actor_role.value,
            ),
            candidates=[SearchCandidate(**item.model_dump()) for item in body.candidates],
            top_k=body.top_k,
        )
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail=exc.detail) from exc
    return RerankResponse(
        results=[
            RankedResult(
                id=item.id,
                title=item.title,
                summary=item.summary,
                relevance_score=item.relevance_score,
            )
            for item in ranked
        ]
    )
