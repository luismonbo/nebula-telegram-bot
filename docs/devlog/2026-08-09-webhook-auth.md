# Webhook authentication

**Related:** [docs/issues/01](../issues/01-webhook-no-auth.md)

## Decision

Fix the unauthenticated webhook with two independent layers instead of one:

1. `function_app.py` route changed from `auth_level=func.AuthLevel.ANONYMOUS` to
   `func.AuthLevel.FUNCTION` — Azure rejects requests missing a valid function key
   before our code runs at all.
2. Added an explicit check of the `X-Telegram-Bot-Api-Secret-Token` header against a
   new `TELEGRAM_WEBHOOK_SECRET` env var, returning 401 on mismatch/missing. This
   confirms the caller is actually Telegram, not just anyone who obtained the function
   key.

Rejected the single-layer alternative (function key only) because the key ends up in
the webhook URL's query string, which Azure/App Insights log by default — so the
"secret" would leak into our own logs. The header-based secret token has no such
exposure and is Telegram's purpose-built mechanism for this.

## Changes

- `function_app.py`: `auth_level=func.AuthLevel.FUNCTION`, secret-token header check.
- `local.settings.json`: added `TELEGRAM_WEBHOOK_SECRET` placeholder.

## Manual steps still required (not automated by this change)

- Generate a function key in the Azure Function App (Portal → Functions →
  `TelegramBotFunction` → Function Keys) and add it as `?code=<key>` to the webhook
  URL registered with Telegram.
- Pick a random secret string, set it as `TELEGRAM_WEBHOOK_SECRET` in both
  `local.settings.json` (local) and the Function App's Application Settings (deployed).
- Re-register the webhook with Telegram's `setWebhook` API, passing both the
  `?code=`-suffixed URL and `secret_token=<same random string>`.
