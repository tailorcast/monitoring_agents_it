#!/usr/bin/env python3
"""Quick test script for Telegram connectivity."""

import asyncio
import logging
import sys
import os
from pathlib import Path
from src.config.loader import ConfigLoader
from src.services.telegram_client import TelegramClient

logging.basicConfig(level=logging.INFO)

def load_env_file(env_path: str = '.env'):
    """Load environment variables from .env file."""
    env_file = Path(env_path)
    if not env_file.exists():
        print(f"⚠️  Warning: {env_path} file not found")
        return

    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            # Parse KEY=VALUE
            if '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

async def main():
    """Test Telegram client connectivity."""
    try:
        # Load environment variables from .env file
        print("Loading environment variables from .env...")
        load_env_file('.env')

        # Load config
        print("Loading configuration...")
        config = ConfigLoader.load_from_file('config/config.yaml')

        # Initialize Telegram client
        print("Initializing Telegram client...")
        print(f"Bot Token: {config.telegram.bot_token[:20]}...{config.telegram.bot_token[-4:]}")
        print(f"Chat ID: {config.telegram.chat_id}")
        telegram = TelegramClient(config.telegram)

        # Test 1: Simple health check
        print("\n[Test 1] Sending health check message...")
        success = await telegram.send_health_check()

        if success:
            print("✅ Health check message sent successfully!")
        else:
            print("❌ Failed to send health check message")
            return 1

        # Test 2: Formatted message
        print("\n[Test 2] Sending formatted test message...")
        test_message = """🧪 **Telegram Client Test**

This is a test of the monitoring system's Telegram integration.

**Status**: 🟢 Working
**Components Tested**:
- Message formatting (Markdown)
- Emoji support
- Multi-line messages

If you can read this, Telegram integration is working correctly!
"""
        success = await telegram.send_message(test_message)

        if success:
            print("✅ Formatted message sent successfully!")
        else:
            print("❌ Failed to send formatted message")
            return 1

        # Test 3: Long message (will be split)
        print("\n[Test 3] Sending long message (>4096 chars)...")
        long_message = "🧪 **Long Message Test**\n\n" + "\n".join([f"Line {i}: Test content for message splitting" for i in range(300)])

        success = await telegram.send_message(long_message)

        if success:
            print("✅ Long message sent successfully (check if split into multiple messages)!")
        else:
            print("❌ Failed to send long message")
            return 1

        # Test 4: Error notification
        print("\n[Test 4] Sending error notification test...")
        test_error = RuntimeError("This is a test error notification")
        await telegram.send_error_notification(test_error, context="Test context")
        print("✅ Error notification sent!")

        print("\n" + "="*60)
        print("✅ All Telegram tests passed!")
        print("="*60)
        print("\nCheck your Telegram chat for 4 messages:")
        print("1. Health check message")
        print("2. Formatted test message")
        print("3. Long message (possibly split into multiple)")
        print("4. Error notification")

        return 0

    except ImportError as e:
        print(f"\n❌ Missing dependency: {e}")
        print("\nInstall with: pip install python-telegram-bot>=20.8")
        return 1

    except FileNotFoundError:
        print("\n❌ Configuration file not found: config/config.yaml")
        print("\nCreate it from: cp config/config.example.yaml config/config.yaml")
        return 1

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
