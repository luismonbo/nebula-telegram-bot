# CI/CD deploy: green pipeline, zero registered functions

**Related:** [2026-08-09-cicd-pipeline.md](2026-08-09-cicd-pipeline.md)

## Symptom

Every run reported success; the portal showed no functions. `az functionapp function list`
returned `[]`. A worker that fails to import registers no functions, and the blob upload
genuinely succeeded, so nothing went red.

## Root cause (two independent defects)

Settled by downloading the deployed package via the SAS URL in
`WEBSITE_RUN_FROM_PACKAGE` and inspecting it. The package itself was well-formed —
`function_app.py`, `host.json`, `src/` (25 entries), `.python_packages/lib/site-packages`
(11,087 entries), `azure/functions/__init__.py` present.

**1. Wheels resolved for the wrong platform.** `pip install --target` ran on
`ubuntu-latest` (glibc 2.39), so it picked wheels the app cannot load. From the deployed
`.dist-info/WHEEL` files:

```
cryptography    cp39-abi3-manylinux_2_34_x86_64     <-- needs glibc >= 2.34
pydantic_core   cp310-cp310-manylinux_2_17_x86_64
numpy           cp310-cp310-manylinux_2_17_x86_64
```

`mcr.microsoft.com/azure-functions/python:4-python3.10` is Debian 11 → **glibc 2.31**, so
the `cryptography` `.so` cannot load. `azure-identity`, `azure-storage-blob`, and `msal`
all import it, and `function_app.py` pulls all three in.

**This is why `./deploy-function.ps1` works and CI did not.** Oryx runs `pip` inside the
Functions image, so it resolves loadable wheels. The runner resolves ones it can't. The
asymmetry was the clue that broke the case open.

**2. The PyPI `asyncio` backport.** `pyproject.toml` declared `asyncio>=3.4.3`; the PyPI
package is a 2015 backport of the **stdlib** module for Python 3.3, and `async` became a
reserved keyword in 3.7. Confirmed in the deployed package: 24 `.py` files but only 21
`.pyc` — `base_events`, `tasks`, and `windows_events` failed to byte-compile, exactly the
files using `async` as an identifier. Reproduced locally on CPython 3.10:

```
File "asyncio/base_events.py", line 296
    future = tasks.async(future, loop=self)
                   ^^^^^
SyntaxError: invalid syntax
```

Since `.python_packages/lib/site-packages` precedes stdlib on `sys.path`, this shadows
real `asyncio` for every transitive importer (aiohttp, langchain, the worker itself).

## Wrong turns (recorded so they aren't repeated)

- **Chasing a remote build.** Linux Consumption deploys via *external package URL* and has
  no Kudu build step, so `remote-build` (Flex Consumption only per the docs matrix),
  `scm-do-build-during-deployment`, and `enable-oryx-build` are all silently ignored.
  Proof: after setting the latter two, `WEBSITE_RUN_FROM_PACKAGE` held a SAS blob URL while
  neither setting was ever written to app settings.
- **Removing the `pip install --target` step** on the assumption Oryx would replace it.
  Nothing did, which shipped source with no dependencies and emptied the app.
- **Core Tools in CI.** `npm install -g azure-functions-core-tools@4` fails (post-install
  CDN 404 for a CLI build newer than any release), and the Microsoft apt feed carries no
  `azure-functions-core-tools-4` for noble or jammy. Moot anyway — building in the runtime
  image achieves the same thing.
- **`az webapp log tail`** returns 404 on Linux Consumption; the plan has no Kudu
  logstream. App Insights is the only log path.

## Fix

- Removed `asyncio` from `pyproject.toml`, `uv.lock`, and `requirements.txt`.
- **Dependencies are now installed inside `mcr.microsoft.com/azure-functions/python:4-python3.10`**
  via `docker run`, so pip resolves wheels against the app's real glibc. This is what
  Oryx does, without needing Kudu.
- Dropped `actions/setup-python`: the interpreter that resolves wheels is the image's.
- Added a **smoke test** that imports `cryptography`, `aiohttp`, `azure.functions`,
  `langchain_openai`, `openai`, `pydub` inside that image and asserts `asyncio` resolves to
  stdlib. Catches both defects above before deploying.
- Added a **post-deploy check** that polls `az functionapp function list` and fails the run
  if nothing registers. Confirmed working — it is what finally turned a run red.
- Single job: the doc template's build/deploy split round-trips through
  upload/download-artifact, stripping the exec bit off `ffmpeg`/`ffprobe`, and it omits
  `include-hidden-files: true`, which would silently drop the hidden `.python_packages`.

## Open

- **Linux Consumption is planned for retirement.** Migrating to Flex Consumption would give
  a real `remote-build: true` and remove the cross-platform wheel problem entirely.
- `docs/` and `tests/` still ship in the package despite `respect-funcignore: true` and
  `.funcignore` listing them. Harmless weight, not yet diagnosed.
- `uv export` emits `pytest` and `python-dotenv` because they sit in `[project].dependencies`
  rather than a dev group — they ship to production (relates to docs/issues/15).
- `deploy-function.ps1` stays as the manual fallback and the way to restore service.
