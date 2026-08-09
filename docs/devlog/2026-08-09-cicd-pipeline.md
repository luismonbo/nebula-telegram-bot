# GitHub Actions CI/CD for Azure Functions deploy

**Related:** [docs/issues/14](../issues/14-host-json-not-tracked.md), [docs/superpowers/specs/2026-08-09-github-actions-cicd-design.md](../superpowers/specs/2026-08-09-github-actions-cicd-design.md)

## Decision

Replaced the manual `deploy-function.ps1` step with a GitHub Actions workflow
(`.github/workflows/deploy.yml`) that deploys on every push to `main`, authenticated
via OIDC (user-assigned managed identity + federated credential — no publish profile,
no long-lived secret stored in GitHub).

Bundled in as a hard blocker fix: `host.json` was gitignored and never committed
(docs/issues/14) — a GitHub Actions runner starts from a clean checkout, so without it
the pipeline had nothing to deploy. Committed a standard default `host.json`.

Dependency handling: the workflow runs `uv export` to regenerate `requirements.txt`
fresh from `uv.lock` before every deploy, so the deployed package's dependencies can
never drift from the lockfile — independent of whatever's committed. Local dev
(Docker Compose, `func start`) is unchanged; `requirements.txt` stays committed there.

## Changes

- `host.json`: added (was missing entirely).
- `.github/workflows/deploy.yml`: added.
- `azure-oidc-setup.ps1`: added — one-time script to create the Azure identity.

## Manual steps still required (not automated)

- Run `azure-oidc-setup.ps1` once, with real subscription/resource-group/app-name
  values filled in.
- Add `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` as GitHub repo
  secrets.
- Edit `AZURE_FUNCTIONAPP_NAME` in `.github/workflows/deploy.yml` to the real Function
  App name.
- `deploy-function.ps1` becomes redundant after the first successful automated
  deploy — left in place as a manual fallback, not removed.
