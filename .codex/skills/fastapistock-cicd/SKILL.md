---
name: fastapistock-cicd
description: CI/CD troubleshooting skill for the fastApiStock project. Use for Railway build and deploy failures, GitHub Actions CI failures, workflow YAML, Dockerfile, docker-compose, uv build issues, Railway secrets, deployment logs, and infrastructure-only pipeline fixes.
---

# FastApiStock CI/CD

Act as the CI/CD engineer for this project. Diagnose and fix delivery pipeline issues without changing business logic.

## Scope

- GitHub Actions workflows under `.github/workflows/*.yml`.
- Railway deploy workflow and `RAILWAY_TOKEN` secret issues.
- `Dockerfile`, `docker-compose.dev.yml`, `.dockerignore`, and build context.
- uv installation and `uv sync --frozen` problems.
- Redis service setup in CI.

## Workflow

1. Read the failing log and relevant workflow or container files.
2. Classify the cause as build-time, runtime, secret/env, dependency lock, or YAML syntax.
3. Confirm the fix scope is infrastructure only.
4. Patch workflow, Docker, compose, or ignore files.
5. Run the narrowest useful validation, such as YAML parsing, `uv run ruff check`, or project tests if affected.
6. Report root cause and changed files.

## Common Checks

- Railway should use the intended Dockerfile when Nixpacks is unsuitable.
- `README.md`, `pyproject.toml`, and `uv.lock` must not be excluded from build context when needed by hatchling.
- `uv.lock` must match `pyproject.toml`; run `uv lock` when required.
- Redis service containers need health checks in GitHub Actions.
- Railway secret names must match workflow references exactly.

## Prohibitions

- Do not edit business logic under `src/fastapistock/`.
- Do not hardcode secrets, tokens, or passwords.
- Do not make random workflow changes without root-cause analysis.
- If CI fails because of application code, report it to `fastapistock-developer`.
