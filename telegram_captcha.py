import asyncio
import os
import truststore
import httpx
from loguru import logger

truststore.inject_into_ssl()


def _get_api_url():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    return f"https://api.telegram.org/bot{token}"


def _get_chat_id():
    return os.getenv("TELEGRAM_CHAT_ID")


def _check_config():
    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set")
    if not os.getenv("TELEGRAM_CHAT_ID"):
        raise RuntimeError("TELEGRAM_CHAT_ID environment variable is not set")


async def send_captcha_image(image_path: str) -> int:
    """Send the CAPTCHA image to the configured Telegram chat.

    Returns the message_id of the sent message.
    """
    _check_config()

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        with open(image_path, "rb") as img:
            resp = await client.post(
                f"{_get_api_url()}/sendPhoto",
                data={
                    "chat_id": _get_chat_id(),
                    "caption": "🔐 CAPTCHA received. Reply to this message with the code.",
                },
                files={"photo": ("captcha.png", img, "image/png")},
            )
        resp.raise_for_status()
        result = resp.json()

        if not result.get("ok"):
            raise RuntimeError(f"Telegram sendPhoto failed: {result}")

        message_id = result["result"]["message_id"]
        logger.info(f"CAPTCHA image sent to Telegram, message_id={message_id}")
        return message_id


async def wait_for_captcha_reply(after_message_id: int, timeout: int = 120) -> str:
    """Poll Telegram for a text reply to the CAPTCHA message.

    Args:
        after_message_id: The message_id of the sent CAPTCHA image.
                          Only replies to this specific message are accepted.
        timeout: Maximum seconds to wait for a reply.

    Returns:
        The CAPTCHA code text from the user's reply.

    Raises:
        TimeoutError: If no reply is received within the timeout period.
    """
    _check_config()

    logger.info(
        f"Waiting up to {timeout}s for CAPTCHA reply (reply_to={after_message_id})..."
    )
    poll_interval = 5
    last_update_id = 0
    import time

    start_time = time.monotonic()

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        # Flush old updates first
        flush_resp = await client.get(
            f"{_get_api_url()}/getUpdates",
            params={"offset": -1, "limit": 1},
        )
        flush_data = flush_resp.json()
        if flush_data.get("ok") and flush_data["result"]:
            last_update_id = flush_data["result"][-1]["update_id"] + 1
        logger.info(f"Flushed old updates, starting from update_id={last_update_id}")

        while (time.monotonic() - start_time) < timeout:
            elapsed = time.monotonic() - start_time
            remaining = timeout - elapsed
            long_poll = min(poll_interval, remaining)
            logger.debug(
                f"Polling getUpdates (offset={last_update_id}, timeout={long_poll}, elapsed={elapsed}s)..."
            )

            resp = await client.get(
                f"{_get_api_url()}/getUpdates",
                params={
                    "offset": last_update_id,
                    "timeout": long_poll,
                },
            )
            data = resp.json()
            logger.debug(f"getUpdates response: {data}")

            if data.get("ok"):
                for update in data.get("result", []):
                    last_update_id = update["update_id"] + 1
                    msg = update.get("message", {})

                    logger.debug(
                        f"Processing update: chat_id={msg.get('chat', {}).get('id')}, text={msg.get('text')}, reply_to={msg.get('reply_to_message', {}).get('message_id')}"
                    )

                    # Accept any text message from the correct chat
                    if str(msg.get("chat", {}).get("id")) == str(
                        _get_chat_id()
                    ) and msg.get("text"):
                        captcha_code = msg["text"].strip()
                        logger.info(f"Received CAPTCHA reply: {captcha_code}")

                        # Acknowledge receipt
                        await client.post(
                            f"{_get_api_url()}/sendMessage",
                            data={
                                "chat_id": _get_chat_id(),
                                "text": f"✅ Received: {captcha_code}. Processing login...",
                                "reply_to_message_id": msg["message_id"],
                            },
                        )
                        return captcha_code

            await asyncio.sleep(1)

    raise TimeoutError(f"No CAPTCHA reply received within {timeout} seconds")


async def send_report(file_path: str, caption: str = "📄 RD Account Report") -> int:
    """Send a document (PDF report) to the configured Telegram chat.

    Returns the message_id of the sent message.
    """
    _check_config()

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        with open(file_path, "rb") as f:
            resp = await client.post(
                f"{_get_api_url()}/sendDocument",
                data={
                    "chat_id": _get_chat_id(),
                    "caption": caption,
                },
                files={"document": (os.path.basename(file_path), f, "application/pdf")},
            )
        resp.raise_for_status()
        result = resp.json()

        if not result.get("ok"):
            raise RuntimeError(f"Telegram sendDocument failed: {result}")

        message_id = result["result"]["message_id"]
        logger.info(f"Report sent to Telegram, message_id={message_id}")
        return message_id


async def send_message(text: str) -> int:
    """Send a text message to the configured Telegram chat."""
    _check_config()

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.post(
            f"{_get_api_url()}/sendMessage",
            data={"chat_id": _get_chat_id(), "text": text},
        )
        resp.raise_for_status()
        result = resp.json()
        return result["result"]["message_id"]


async def poll_for_commands(on_report_command):
    """Background loop that polls Telegram for /report commands.

    Args:
        on_report_command: An async callable to invoke when /report is received.
    """
    _check_config()
    logger.info(
        "Telegram bot command listener started. Send /report to generate a report."
    )
    last_update_id = 0

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        # Flush old updates
        try:
            flush_resp = await client.get(
                f"{_get_api_url()}/getUpdates",
                params={"offset": -1, "limit": 1},
            )
            logger.debug(
                f"Flush response status={flush_resp.status_code} body={flush_resp.text[:200]}"
            )
            if flush_resp.status_code == 200 and flush_resp.text.strip():
                flush_data = flush_resp.json()
                if flush_data.get("ok") and flush_data["result"]:
                    last_update_id = flush_data["result"][-1]["update_id"] + 1
        except Exception as e:
            logger.error(f"Failed to flush old updates: {e}")

        while True:
            try:
                resp = await client.get(
                    f"{_get_api_url()}/getUpdates",
                    params={"offset": last_update_id, "timeout": 30},
                )
                logger.debug(
                    f"getUpdates status={resp.status_code} body={resp.text[:200]}"
                )

                if resp.status_code != 200 or not resp.text.strip():
                    logger.warning(
                        f"Unexpected response from Telegram: status={resp.status_code}"
                    )
                    await asyncio.sleep(5)
                    continue

                data = resp.json()

                if data.get("ok"):
                    for update in data.get("result", []):
                        last_update_id = update["update_id"] + 1
                        msg = update.get("message", {})

                        if (
                            str(msg.get("chat", {}).get("id")) == str(_get_chat_id())
                            and msg.get("text", "").strip().lower() == "/report"
                        ):
                            logger.info("Received /report command from Telegram")
                            await send_message("⏳ Starting report generation...")
                            try:
                                await on_report_command()
                            except Exception as e:
                                logger.error(f"Report generation failed: {e}")
                                await send_message(
                                    f"❌ Report generation failed: {str(e)}"
                                )
            except Exception as e:
                logger.error(f"Telegram polling error: {e}")
                await asyncio.sleep(5)
