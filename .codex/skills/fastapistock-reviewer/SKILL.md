---
name: fastapistock-reviewer
description: Code review skill for the fastApiStock project. Use after fastapistock-developer completes implementation and before fastapistock-qa. Review changed files for correctness, security, typing, project rule violations, tests, and readiness for QA with a PASS or FAIL verdict.
---

# FastApiStock Reviewer

Act as the pre-QA code reviewer. Review changed files and produce a structured PASS/FAIL report. Findings must lead, ordered by severity.

## Review Inputs

- `git diff --name-only main` or the current branch diff.
- `AGENTS.md` project rules.
- `specs/<feature>/handoff-dev.json` when present.
- Changed source and test files. Skip lock files, generated files, migrations, and bulky fixtures unless directly relevant.

## Review Checklist

- Correctness against acceptance criteria.
- Security: no hardcoded secrets, no string-built SQL, request validation present.
- Type completeness: public functions typed, no unjustified `Any`.
- Logging: no `print()`.
- Error handling: no bare `except:`, external IO has defensive handling.
- API routes: response envelope and rate limiting.
- External requests: timeout configured.
- Taiwan stock calls: random delay and local cache.
- Yahoo Finance premarket: do not use `ticker.info['preMarketPrice']`.
- Style: single quotes where practical, 88-char line limit, small functions.
- Tests: meaningful coverage for changed behavior and edge cases.

## Output Format

```markdown
# Code Review Report
**Feature**: <feature>
**Branch**: <branch>
**Reviewed files**: <list>
**Date**: <date>

## Summary
PASS / FAIL / PASS_WITH_WARNINGS

## Issues Found
| File | Line | Severity | Issue |
|------|------|----------|-------|
| ... | ... | ERROR/WARN/INFO | ... |

## Project Rule Violations
List violations of AGENTS.md and skill rules.

## Recommendation
- PASS: safe to use fastapistock-qa
- FAIL: return to fastapistock-developer with blocking issues
```

## Verdict Rules

- Use `FAIL` for correctness bugs, security issues, missing required validation, missing rate limiting on new routes, or broken tests.
- Use `PASS_WITH_WARNINGS` for non-blocking maintainability or coverage suggestions.
- Use `PASS` only when QA can proceed.
