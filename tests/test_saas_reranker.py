from typing import Any

from saas_search.saas_reranker import SearchCandidate, TenantContext, TenantSearchReranker


class RecordingGateway:
    def __init__(self) -> None:
        self.query = ""

    def rerank(
        self,
        query: str,
        candidates: list[str],
        top_k: int,
        *,
        model: str = "auto",
        vendor: str = "auto",
    ) -> dict[str, Any]:
        self.query = query
        assert model == "auto"
        assert vendor == "auto"
        assert top_k == 2
        assert "Restore a suspended workspace" in candidates[1]
        return {
            "ok": True,
            "data": {
                "results": [
                    {"index": 1, "relevance_score": 0.97},
                    {"index": 0, "relevance_score": 0.31},
                ]
            },
            "error": None,
            "metadata": {"vendor": "selected-vendor"},
        }


def test_suspended_account_admin_gets_restore_guide_first() -> None:
    gateway = RecordingGateway()
    reranker = TenantSearchReranker(gateway)

    ranked = reranker.rank(
        query="How do I let the team sign in again?",
        tenant=TenantContext(
            onboarding_stage="completed",
            account_status="suspended",
            actor_role="admin",
        ),
        candidates=[
            SearchCandidate("invite", "Invite teammates", "Add members during onboarding."),
            SearchCandidate(
                "restore",
                "Restore a suspended workspace",
                "An admin reviews billing status and restores account access.",
            ),
        ],
        top_k=2,
    )

    assert "account=suspended" in gateway.query
    assert "actor=admin" in gateway.query
    assert [item.id for item in ranked] == ["restore", "invite"]
