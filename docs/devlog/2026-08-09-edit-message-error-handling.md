# Stop swallowing real editMessageText failures

**Related:** [docs/issues/03](../issues/03-swallowed-edit-message-errors.md)

## Decision

`_is_message_unchanged_error()` unconditionally returned `True`, so `edit_message`
treated every failure — rate limiting, bad chat ID, malformed HTML, network error — as
the benign "message content unchanged" case and reported success (returning
`message_id`) without ever logging the real problem.

Fixed by making `_make_request` return the parsed Telegram error body (with its
`description` field) instead of `None` on non-2xx responses, so `edit_message` can
actually inspect *why* it failed. `_is_message_unchanged_error` now takes that
description and only matches Telegram's specific "message is not modified" text; every
other failure is logged and `edit_message` returns `None` instead of a false success.

`send_message` needed a matching update (`response.get("ok")` check) since it also
consumed `_make_request`'s return value and would otherwise hit a `KeyError` on the new
error-dict shape. `get_file` already checked `"result" in response` explicitly, so it
needed no change.

## Changes

- `src/services/telegram_service.py`: `_make_request` returns the error body on
  failure; `_is_message_unchanged_error` takes a description and checks for the
  specific benign case; `edit_message`/`send_message` updated for the new contract.
- `tests/test_telegram_service.py`: added — first real test in the repo. Covers
  successful edit, the benign unchanged-content case, a genuine error (rate limit) no
  longer being swallowed, and no-response handling. Run via `uv run pytest` (plain
  `pytest`/`python -m pytest` uses the system interpreter, which lacks project deps).
