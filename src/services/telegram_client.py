"""Telegram bot client for sending monitoring reports."""

import asyncio
import logging
from typing import List, Optional

try:
    from telegram import Bot
    from telegram.constants import ParseMode
    import telegram.error
except ImportError:
    Bot = None
    ParseMode = None
    telegram = None

from ..config.models import TelegramConfig


class TelegramClient:
    """
    Telegram bot client for sending monitoring reports.

    Handles message splitting for long messages, retry logic,
    and Markdown formatting.
    """

    def __init__(self, config: TelegramConfig, logger: logging.Logger = None):
        """
        Initialize Telegram client.

        Args:
            config: Telegram configuration
            logger: Optional logger instance

        Raises:
            ImportError: If python-telegram-bot not installed
        """
        if Bot is None:
            raise ImportError(
                "python-telegram-bot library not installed. "
                "Install with: pip install python-telegram-bot>=20.8"
            )

        self.bot = Bot(token=config.bot_token)
        self.chat_id = config.chat_id
        self.logger = logger or logging.getLogger(__name__)

    async def send_message(
        self,
        message: str,
        parse_mode: str = None
    ) -> bool:
        """
        Send message to Telegram chat.

        Automatically splits messages longer than 4096 characters.
        Retries on failure with exponential backoff.

        Args:
            message: Message text to send
            parse_mode: Parse mode (Markdown, MarkdownV2, HTML, or None)

        Returns:
            bool: True if sent successfully, False otherwise
        """
        # Default to Markdown if available
        if parse_mode is None and ParseMode is not None:
            parse_mode = ParseMode.MARKDOWN

        try:
            # Telegram has 4096 char limit per message
            if len(message) > 4096:
                self.logger.info(
                    f"Message length {len(message)} exceeds limit, splitting"
                )
                await self._send_long_message(message, parse_mode)
            else:
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode=parse_mode
                )

            self.logger.info("Telegram message sent successfully")
            return True

        except telegram.error.BadRequest as e:
            if "Can't parse entities" in str(e):
                self.logger.warning(
                    f"Markdown parsing failed: {e}. Retrying without formatting..."
                )
                # Retry without parse mode (plain text)
                try:
                    if len(message) > 4096:
                        await self._send_long_message(message, parse_mode=None)
                    else:
                        await self.bot.send_message(
                            chat_id=self.chat_id,
                            text=message,
                            parse_mode=None
                        )
                    self.logger.info("Telegram message sent successfully (plain text)")
                    return True
                except Exception as retry_error:
                    self.logger.error(
                        f"Failed to send Telegram message even as plain text: {retry_error}",
                        exc_info=True
                    )
                    return False
            else:
                self.logger.error(
                    f"Failed to send Telegram message: {e}",
                    exc_info=True
                )
                return False

        except Exception as e:
            self.logger.error(
                f"Failed to send Telegram message: {e}",
                exc_info=True
            )
            return False

    async def _send_long_message(
        self,
        message: str,
        parse_mode: Optional[str]
    ):
        """
        Split and send long messages.

        Args:
            message: Long message to split and send
            parse_mode: Parse mode for formatting
        """
        chunks = self._split_message(message, max_length=4000)

        self.logger.info(f"Sending message in {len(chunks)} chunk(s)")

        for i, chunk in enumerate(chunks):
            if i > 0:
                # Rate limit: wait 1 second between messages
                await asyncio.sleep(1)

            await self.bot.send_message(
                chat_id=self.chat_id,
                text=chunk,
                parse_mode=parse_mode
            )

            self.logger.debug(f"Sent chunk {i+1}/{len(chunks)}")

    def _split_message(self, message: str, max_length: int = 4000) -> List[str]:
        """
        Split message at logical boundaries (newlines).

        Args:
            message: Message to split
            max_length: Maximum length per chunk (leave buffer for Telegram)

        Returns:
            List of message chunks
        """
        if len(message) <= max_length:
            return [message]

        chunks = []
        current_chunk = ""

        for line in message.split('\n'):
            # Check if adding this line would exceed limit
            if len(current_chunk) + len(line) + 1 > max_length:
                # Save current chunk and start new one
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line
            else:
                # Add line to current chunk
                current_chunk += '\n' + line if current_chunk else line

        # Don't forget the last chunk
        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    async def send_error_notification(self, error: Exception, context: str = ""):
        """
        Send error notification to Telegram.

        Args:
            error: Exception that occurred
            context: Additional context about the error
        """
        error_type = type(error).__name__
        error_msg = str(error)

        message = f"""🚨 **Monitoring System Error**

**Error Type**: {error_type}
**Message**: {error_msg}
"""

        if context:
            message += f"\n**Context**: {context}"

        message += "\n\nThe monitoring cycle failed to complete. Check logs for details."

        try:
            await self.send_message(message)
        except Exception as e:
            # Last resort: log error
            self.logger.error(
                f"Failed to send error notification to Telegram: {e}",
                exc_info=True
            )

    async def send_health_check(self) -> bool:
        """
        Send test message to verify Telegram connectivity.

        Returns:
            bool: True if test message sent successfully
        """
        test_message = "✅ Monitoring system health check - Telegram connection OK"
        return await self.send_message(test_message)
