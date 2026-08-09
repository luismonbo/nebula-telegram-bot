import asyncio
import datetime
import io
import logging
import os

import aiohttp
from azure.storage.blob.aio import BlobServiceClient

from src.services import openai_service, telegram_service


class AudioProcessor:
    def __init__(
        self,
        telegram_service: telegram_service.TelegramService,
        openai_service: openai_service.OpenAIService,
    ):
        self.openai_service = openai_service
        self.telegram_service = telegram_service

    async def download_telegram_file(self, file_id, token):

        async with aiohttp.ClientSession() as session:
            # Get file path from Telegram's getFile endpoint
            logging.info(f"Getting file path for file_id: {file_id}")
            response = await session.get(
                f"https://api.telegram.org/bot{token}/getFile?file_id={file_id}"
            )
            logging.info(f"Response status: {response.status}")

            result = await response.json()
            file_path = result.get("result", {}).get("file_path")

            if not file_path:
                logging.error(f"Failed to get file path for file_id: {file_id}")
                raise Exception("Failed to get file path")
            # Download the file using the file path
            file_url = f"https://api.telegram.org/file/bot{token}/{file_path}"
            response = await session.get(file_url)
            return (
                await response.read(),
                file_path.split(".")[-1],
            )

    async def save_audio_to_blob(
        self, chat_id, m4a_audio_data, timestamp, container_name="filecontainer"
    ):
        try:
            # TODO: Probably use the blob_service_client instead of this whole thing
            async with BlobServiceClient.from_connection_string(
                os.getenv("AdditionalStorage")
            ) as blob_service_client:
                blob_name = f"{chat_id}_{timestamp}.m4a"
                blob_client = blob_service_client.get_blob_client(
                    container=container_name, blob=blob_name
                )
                await blob_client.upload_blob(m4a_audio_data)

            logging.info(f"Audio message saved to blob storage at {blob_name}")
        except Exception as e:
            logging.error(f"Failed to save audio file to blob storage: {str(e)}")

    def convert_to_m4a(self, audio_bytes, input_format):

        logging.info("Converting audio to m4a format")
        cwd = os.getcwd()

        # Add to PATH
        os.environ["PATH"] = os.pathsep.join([os.getcwd(), os.environ.get("PATH", "")])
        logging.info(f"Updated PATH: {os.environ['PATH']}")

        from pydub import AudioSegment

        AudioSegment.converter = os.path.join(cwd, "ffmpeg")
        AudioSegment.ffprobe = os.path.join(cwd, "ffprobe")

        logging.info(f"Converting from {input_format} to m4a")
        audio = AudioSegment.from_ogg(io.BytesIO(audio_bytes))
        m4a_audio_io = io.BytesIO()
        audio.export(m4a_audio_io, format="mp4")
        m4a_audio_io.seek(0)
        return m4a_audio_io.read()

    async def process_audio_message(self, message, token):
        # Extract audio file details from the message
        audio = message.get("audio")
        voice = message.get("voice")
        audio_file_id = audio.get("file_id") if audio else voice.get("file_id")
        chat_id = message.get("chat", {}).get("id", "No chat id")
        logging.info(
            f"Processing audio message_id={message.get('message_id')} chat_id={chat_id}"
        )
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%d%H%M%S"
        )

        # Download the audio file from Telegram
        audio_data, file_extension = await self.download_telegram_file(
            audio_file_id, token
        )
        if not audio_data:
            logging.error(
                f"Failed to download audio file with file_id: {audio_file_id}"
            )
            return

        if file_extension != "m4a":
            # Convert the audio data to M4A format
            try:
                logging.info(
                    f"Converting audio data to M4A format: {len(audio_data)} in {file_extension} format"
                )
                audio_data = self.convert_to_m4a(audio_data, file_extension)
            except Exception as e:
                logging.error(f"Failed to convert audio to m4a format: {e}")
                return

        # Save the M4A audio file to Azure Blob Storage
        # await save_audio_to_blob(chat_id, audio_data, timestamp)

        # Transcribe the audio message
        transcription, language = await self.openai_service.transcribe_audio(
            audio_data=audio_data
        )

        logging.info(f"Processed incoming audio message from chat: {chat_id}")

        return transcription, language
