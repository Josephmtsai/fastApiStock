# Tasks: 20260405 Railway Deployment via GitHub Actions

**Input**: `specs/main/task/20260405task-railway-deploy.md`
**Branch**: `feature/stock`
**Date**: 2026-04-05

## Feature Summary

Deploy the FastAPI stock service to Railway via GitHub Actions.
On every push to `main`, GitHub Actions runs `railway up` using
`RAILWAY_TOKEN` stored as a repository secret. No changes to
`config.py` or `redis_cache.py` — env vars (`REDIS_HOST`, `REDIS_PORT`,
`REDIS_PASSWORD`, `TELEGRAM_TOKEN`) are configured directly in the
Railway project dashboard.

---

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [ ] T001 Create `.github/workflows/deploy-railway.yml` with push-to-main trigger, Railway CLI install, and `railway up --detach` step

---

## Phase 2: US1 — Automated Railway deploy on push to main

**Story goal**: Pushing to `main` triggers Railway deployment automatically.

**Independent test**: Push a commit to `main`; GitHub Actions run passes; Railway dashboard shows new deployment.

**Railway setup (manual, one-time)**:
1. Create Railway project and link the repo
2. Add `RAILWAY_TOKEN` as a GitHub repo secret (Settings → Secrets → Actions)
3. Set `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD`, `TELEGRAM_TOKEN` in Railway project variables

- [ ] T002 [US1] Add `RAILWAY_TOKEN` to GitHub repo secrets (manual step — document in README or .env.example)
- [ ] T003 [P] [US1] Update `.env.example` to list all required env vars with comments for Railway dashboard config

---

## Phase 3: Polish

- [ ] T004 [P] Verify `uv run ruff check . && uv run mypy src/` both pass clean

---

## Dependencies

```
T001 → T002 (workflow file must exist before setting up secrets)
T003 (independent)
```

## MVP Scope

T001 + T002 — workflow file plus Railway token secret is all that's needed for auto-deploy.
