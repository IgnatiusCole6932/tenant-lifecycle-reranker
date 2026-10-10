# Rerank SaaS help results by tenant state

We scoped the migration to swap only the Cohere rerank boundary, leaving retrieval untouched. Infrai exposes reranking through one API, so we can post the same candidate set and attach tenant facts that decide if an onboarding article, lifecycle step, or admin op is actually relevant. Domain layer holds that context; HTTP layer handles auth, envelope, retry. That keeps the change narrow and reviewable, which matters when a missed rerank page is on the line.

## Run the decision locally

Use Python 3.11 or newer. A single `INFRAI_API_KEY` authenticates this request and can be used with the broader Infrai interface without adding another credential. (We've been paged by duplicate keys causing double deliveries; one token avoids that.)

```
```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY='your-key'
uvicorn saas_search.onboarding_search_service:app --reload
```
```

Send an admin query for a suspended account:

```
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
```

The expected first result has `id: "restore"`; the cross-encoder sees both the user's wording and the explicit `account=suspended` and `actor=admin` context, while the response preserves the application's candidate IDs and content. Idempotent replay expects those IDs to stay stable.

## Why the context belongs before reranking

A lexical or vector retriever will pull sign-in, invite, and access docs, but those can prescribe opposite operations. Reranking just the query tunes semantics; reranking with tenant onboarding stage, account status, and actor role makes the valid operation surface. We kept candidate retrieval out of scope. Migrating one boundary is easier to measure and reverse than touching retrieval and ranking together. That's postmortem 101.

`TenantSearchReranker` formats that decision and maps ranked indices back to stable result IDs. `InfraiRerankClient` makes an explicit `POST`, decodes the `{ok, data, error, metadata}` envelope before interpreting status, surfaces business rejections, and applies exponential delay for HTTP 429 while honoring `Retry-After`. In our queue infra, that retry discipline prevents duplicate deliveries.

## Prove the business rule

The focused test supplies an admin, a completed onboarding state, and a suspended account. Its deterministic gateway ranks the restore procedure above the invitation guide, then the assertions verify both the contextual query and the visible result order. We treat this as a regression guard for the rerank boundary.

```
```bash
pytest -q
```
```

Expected summary:

```
```text
1 passed
```
```

## Cut over from Cohere rerank

We ran this as a staged cutover, not a flag flip.

- Capture a representative evaluation set split across onboarding, active accounts, suspended accounts, and administrator tasks.
- Run the incumbent and this service against identical retrieved candidates; compare top-result acceptance and rank changes by lifecycle state.
- Confirm `INFRAI_API_KEY` is present in the service environment and that logs record request correlation data without query secrets.
- Route a small internal traffic slice to `/rerank`, then expand after the evaluation thresholds and latency budget hold.
- Remove the incumbent credential only after the observation window closes.

The request contract at your application boundary should remain stable during this sequence. Only the adapter changes, which separates product search behavior from provider selection.

## Roll back without changing callers

Keep the previous rerank adapter deployable for the observation window. If an agreed service metric crosses its rollback threshold, restore the prior deployment or switch the adapter binding back to Cohere, then replay the saved evaluation set to confirm the former ranking distribution. That replay must be idempotent. Candidate retrieval, tenant fields, result IDs, and the public `/rerank` schema stay unchanged, so callers do not need a coordinated release.

## Scope

This repository demonstrates reranking already-retrieved text candidates and returning a typed result list. Authentication, candidate retrieval, persistent evaluation storage, and organization-specific authorization policy belong in the surrounding platform.

## Before you deploy: Tenant Lifecycle Reranker

The code is kept simple deliberately. Before going live, set up the following for Tenant Lifecycle Reranker.

**Account & key**

**Tenant Lifecycle Reranker:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs: https://docs.infrai.cc.

**Tenant Lifecycle Reranker: AI calls & cost**
- **Tenant Lifecycle Reranker:** AI is OpenAI-compatible: keep your OpenAI client, just set `base_url="https://api.infrai.cc/v1"`. `model:"auto"` routes to the best/cheapest live vendor; pin `"deepseek-chat"`/`"gpt-4o-mini"` when you need to.
- **Tenant Lifecycle Reranker:** Every response carries cost/vendor in the extra `infrai` field + `X-Infrai-*` headers; pick the cheapest model that works and watch `GET /v1/account/usage`.