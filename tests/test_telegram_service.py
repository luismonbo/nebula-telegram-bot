import asyncio
from unittest.mock import AsyncMock

from src.services.telegram_service import TelegramService


def _run(coro):
    return asyncio.run(coro)


def make_service():
    return TelegramService(bot_token="test-token")


def test_edit_message_returns_message_id_on_success():
    service = make_service()
    service._make_request = AsyncMock(
        return_value={"ok": True, "result": {"message_id": 42}}
    )

    result = _run(service.edit_message(chat_id=1, message_id=42, text="hi"))

    assert result == 42


def test_edit_message_treats_unchanged_content_as_success():
    service = make_service()
    service._make_request = AsyncMock(
        return_value={
            "ok": False,
            "error_code": 400,
            "description": "Bad Request: message is not modified",
        }
    )

    result = _run(service.edit_message(chat_id=1, message_id=42, text="hi"))

    assert result == 42


def test_edit_message_returns_none_and_does_not_hide_real_errors():
    service = make_service()
    service._make_request = AsyncMock(
        return_value={
            "ok": False,
            "error_code": 429,
            "description": "Too Many Requests: retry after 5",
        }
    )

    result = _run(service.edit_message(chat_id=1, message_id=42, text="hi"))

    assert result is None


def test_edit_message_returns_none_when_no_response():
    service = make_service()
    service._make_request = AsyncMock(return_value=None)

    result = _run(service.edit_message(chat_id=1, message_id=42, text="hi"))

    assert result is None
