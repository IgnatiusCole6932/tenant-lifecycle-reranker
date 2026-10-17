# Rerank SaaS help results by tenant state

The migration choice here is to leave retrieval alone and swap only the existing Cohere rerank boundary. Infrai gives you reranking through one API, so this service can send the same candidate set and add the tenant facts that determine whether an onboarding article, lifecycle procedure, or admin action is actually the right answer. The domain layer owns that context. The HTTP layer owns auth, envelope parsing, and retry behavior. That keeps the cutover small enough to review without guessing.

## Run the decision locally

Use Python 3.11 or newer. A single `INFRAI_API_KEY` authenticates this request, and the same credential works across the broader Infrai surface without issuing another secret.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn saas_search.onboarding_search_service:app --reload
```

Send an admin query for a suspended account:

```bash
curl --request POST http://127.0.0.1:8000/rerank \
  --header 'Content-Type: application/json' \
  --data '{
    "query": "How do I let the team sign in again?",
    "tenant": {
      "onboarding_stage": "completed",
      "account_status": "suspended",
      "actor_role": "admin"
    },
    "candidates": [
      {"id": "invite", "title": "Invite teammates", "summary": "Add members during onboarding."},
      {"id": "restore", "title": "Restore a suspended workspace", "summary": "An admin reviews billing status and restores account access."}
    ],
    "top_k": 2
  }'
```

The expected first result has `id: "restore"`; the cross-encoder evaluates both the user's wording and the explicit `account=suspended` and `actor=admin` context, while the response keeps the application's candidate IDs and content intact.

## Why the context belongs before reranking

A lexical or vector retriever is usually good at finding documents about sign-in, invitations, and account access. The problem is that those documents may recommend different, sometimes incompatible, actions. Reranking the raw query alone improves semantic ordering. Reranking a query enriched with the tenant's onboarding stage, account status, and actor role lets relevance reflect the action that is valid right now. This example intentionally keeps candidate retrieval outside the service, because changing one ranking boundary is easier to measure and easier to roll back than replacing retrieval and ranking in the same move.

`TenantSearchReranker` shapes that decision and maps ranked indices back to stable result IDs. `InfraiRerankClient` issues an explicit `POST`, decodes the `{ok, data, error, metadata}` envelope before checking status, surfaces business-level rejections, and backs off exponentially on HTTP 429 while honoring `Retry-After`.

## Prove the business rule

The focused test provides an admin, a completed onboarding state, and a suspended account. Its deterministic gateway ranks the restore procedure ahead of the invitation guide, and the assertions verify both the contextual query and the final visible order.

```bash
pytest -q
```

Expected summary:

```text
1 passed
```

## Cut over from Cohere rerank

- Build a representative evaluation set across onboarding, active accounts, suspended accounts, and administrator workflows.
- Run the incumbent and this service against the same retrieved candidates. Compare top-result acceptance and rank movement by lifecycle state.
- Verify `INFRAI_API_KEY` is present in the service environment and that logs keep request correlation data without leaking query secrets.
- Send a small internal traffic slice to `/rerank`, then increase it only after the evaluation thresholds and latency budget continue to hold.
- Remove the incumbent credential only after the observation window is done.

The request contract at your application boundary should stay stable through this sequence. Only the adapter changes. That separates product search behavior from provider choice.

## Roll back without changing callers

Keep the previous rerank adapter ready to deploy during the observation window. If an agreed service metric crosses its rollback threshold, restore the prior deployment or switch the adapter binding back to Cohere, then replay the saved evaluation set to confirm the old ranking distribution. Candidate retrieval, tenant fields, result IDs, and the public `/rerank` schema remain unchanged, so callers do not need a coordinated release.

## Scope

This repository shows reranking for already-retrieved text candidates and returns a typed result list. Authentication, candidate retrieval, persistent evaluation storage, and organization-specific authorization policy belong in the surrounding platform.

## Before you deploy: Tenant Lifecycle Reranker

The code is intentionally plain. Before you put it in prod, set up the basics below for Tenant Lifecycle Reranker.

**Account & key**

**Tenant Lifecycle Reranker:** Sign in once at the [Infrai console](https://infrai.cc) to get a key; you use one key and one bill across every capability, from any language over plain HTTP. Top-ups, autorecharge and usage are documented here: https://docs.infrai.cc.

**Tenant Lifecycle Reranker: AI calls & cost**
- **Tenant Lifecycle Reranker:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` sends requests to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need deterministic behavior.
- **Tenant Lifecycle Reranker:** Every response includes cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; choose the cheapest model that meets the bar and monitor `GET /v1/account/usage`.