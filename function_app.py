import logging
import os

import azure.functions as func

from src.commands.command_registry import CommandRegistry
from src.commands.start_command import StartCommand
from src.db.users import NebulaUsers
from src.message_processing.audio_processor import AudioProcessor
from src.message_processing.message_handler import MessageHandler
from src.services.llm_service import LLMService
from src.services.telegram_service import TelegramService

telegram_service = TelegramService(os.getenv("TELEGRAM_BOT_TOKEN", ""))
llm_service = LLMService(provider="openai", api_key=os.getenv("OPENAI_API_KEY", ""))
audio_processor = AudioProcessor(telegram_service, llm_service)

user_db = NebulaUsers(os.getenv("COSMOSDB_CONNECTION_STRING", ""))

message_handler = MessageHandler(
    llm_service=llm_service,
    telegram_service=telegram_service,
    audio_processor=audio_processor,
)

app = func.FunctionApp()

TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")


@app.function_name("TelegramBotFunction")
@app.route(route="nebula", methods=["POST"], auth_level=func.AuthLevel.FUNCTION)
async def telegram_bot_function(req: func.HttpRequest) -> func.HttpResponse:
    logging.info("Python HTTP trigger function received a request from Telegram Bot.")

    if req.headers.get("X-Telegram-Bot-Api-Secret-Token") != TELEGRAM_WEBHOOK_SECRET:
        logging.warning("Rejected webhook request with missing/invalid secret token.")
        return func.HttpResponse("Unauthorized", status_code=401)

    try:
        req_body = req.get_json()

        # Check if user in db
        username = req_body.get("message").get("from", {}).get("username", {})
        chat_id = req_body.get("message").get("chat").get("id")

        logging.info(f"Received message from {username}: {req_body}")
        logging.info(user_db.get_user(username))
        if user_db.get_user(username):
            response_message = await message_handler.handle_update(req_body)
            return response_message
        else:
            logging.info(f"Username: {username} not a subscriber.")
            await telegram_service.send_message(
                chat_id=chat_id,
                text="Sorry Nebula is for subscribers only at the moment.",
            )
            return func.HttpResponse(
                f"Ignored username {username} as it is not a subscriber."
            )
    except Exception as e:
        logging.error(f"An error occurred while processing the request: {e}")
        return func.HttpResponse(
            "An error occurred while processing the request.", status_code=500
        )
