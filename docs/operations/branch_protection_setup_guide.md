---
title: Branch Protection Setup Guide
description: Exact repository branch protection and ruleset settings required to enforce CODEOWNERS, CI checks, and dependency review gates.
ms.date: 2026-03-27
ms.topic: how-to
author: SRE Agent Engineering Team
status: APPROVED
---

## Scope

This guide configures branch protection for the default branch using the current repository controls:

* `.github/CODEOWNERS`
* `.github/workflows/ci.yml`
* `.github/workflows/dependency-review.yml`

Target outcome:

* No merge to `main` without passing CI and dependency review checks
* No merge to `main` without required reviewer approval and code owner coverage

## Required status checks

Use the exact job check names below in branch protection or rulesets.

| Workflow file | Job id | Required check name |
|---|---|---|
| `.github/workflows/ci.yml` | `lint-type-unit` | `lint-type-unit` |
| `.github/workflows/dependency-review.yml` | `dependency-review` | `dependency-review` |
| `.github/workflows/security-gates.yml` | `security-gates` | `security-gates` |

> [!IMPORTANT]
> Required checks are job names, not workflow file names. If a job id changes in workflow YAML, update the required check list in branch protection settings.

## Recommended branch protection values for `main`

| Setting | Value |
|---|---|
| Require a pull request before merging | Enabled |
| Required approving reviews | 1 minimum |
| Require review from Code Owners | Enabled |
| Dismiss stale pull request approvals when new commits are pushed | Enabled |
| Require approval of the most recent reviewable push | Enabled |
| Require status checks to pass before merging | Enabled |
| Required status checks | `lint-type-unit`, `dependency-review`, `security-gates` |
| Require branches to be up to date before merging | Enabled |
| Require conversation resolution before merging | Enabled |
| Require signed commits | Enabled if team policy supports signed commits |
| Require linear history | Enabled |
| Do not allow bypassing the above settings | Enabled |
| Restrict who can push to matching branches | Enabled for automation and release maintainers only |
| Allow force pushes | Disabled |
| Allow deletions | Disabled |

## Setup steps in GitHub UI

1. Open repository settings.
2. Go to branch protection rules or rulesets.
3. Create or edit the rule for `main`.
4. Enable pull request requirements and code owner reviews.
5. Enable required status checks and add:
   * `lint-type-unit`
   * `dependency-review`
   * `security-gates`
6. Enable conversation resolution and strict up-to-date requirement.
7. Disable bypass, force push, and deletion.
8. Save the rule and verify it applies to `main`.

## Verification checklist

Use this checklist after enabling settings:

* Open a test pull request with a docs or code change.
* Confirm `lint-type-unit`, `dependency-review`, and `security-gates` checks appear and must pass.
* Confirm at least one approval is required.
* Confirm code owner review is requested based on `.github/CODEOWNERS`.
* Push a new commit and confirm stale approvals are dismissed.
* Confirm merge is blocked until checks and approvals are satisfied.

## Troubleshooting

| Symptom | Likely cause | Resolution |
|---|---|---|
| Required check not found in settings | No successful run exists yet for that job name | Run the workflow once on a pull request, then add the check |
| Check name mismatch after workflow edit | Job id was renamed | Update required checks to match current job ids |
| Code owner review not requested | Pattern mismatch in `CODEOWNERS` | Validate path case sensitivity and pattern precedence |
| Merge is possible without checks | Rule does not apply to target branch | Confirm rule target is `main` and no conflicting broader rule overrides it |

## Change control note

Any update to the following files requires reviewing this guide and branch protection settings together:

* `.github/CODEOWNERS`
* `.github/workflows/ci.yml`
* `.github/workflows/dependency-review.yml`
* `.github/workflows/security-gates.yml`
