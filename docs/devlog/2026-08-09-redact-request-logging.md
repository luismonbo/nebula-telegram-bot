# Fix username crash, redact PII from request logs

**Related:** [docs/issues/02](../issues/02-username-crash-on-missing-username.md), [docs/issues/10](../issues/10-logging-full-request-bodies.md)

## Decision

Picked up the two highest-priority open issues after webhook auth: #02 (Critical,
crash) and #10 (High, PII leakage).

**#02 — crash fix only.** `username = ...get("username", {})` defaulted to a dict when
Telegram users have no `@username` set (common), and `username.lower()` downstream
raised `AttributeError`, swallowed by a bare `except` into a generic 500. Fixed by
defaulting to `None` and guarding with `if username and user_db.get_user(username)`
before ever querying the DB. Also removed a redundant duplicate `get_user()` call that
existed only to feed a log line.

Deferred the second half of #02 (migrating the allowlist to key on numeric `user_id`
instead of mutable `username`) — the user wants to move off Cosmos DB to Azure Tables
later, so reworking the Cosmos schema now would be throwaway work. Left a note on the
issue to revisit once the storage backend is decided.

**#10 — redact full-body logging.** `function_app.py` logged the entire incoming
Telegram update (message text, audio metadata) to Azure Function logs on every request.
While fixing #02 in the same lines, also swept for the same pattern elsewhere and found
two more spots doing it (`message_handler.py`, `audio_processor.py` — both log the full
audio message dict, which includes chat/from PII). All three now log only non-sensitive
identifiers (`message_id`, `chat_id`, `duration`), never the full payload.

## Changes

- `function_app.py`: guard against missing username before DB lookup; log identifiers
  only, not the full request body.
- `src/message_processing/message_handler.py`: `handle_audio` logs identifiers only.
- `src/message_processing/audio_processor.py`: `process_audio_message` logs identifiers
  only.

## Follow-up

- #02's `user_id` allowlist migration is still open, blocked on the Cosmos DB → Azure
  Tables decision.
