"""Telegram bot: when an original CAMMED invoice PDF is posted in the group,
reply with the 2-page discounted invoice. The bot can't see invoices it posts itself,
so for those someone replies /discount to the invoice."""

import io
import logging
import os

from dotenv import load_dotenv
from telegram import Message, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, TypeHandler, filters

from invoice import InvoiceError, NotAnInvoice, fixed_items, fixed_items_source, generate

load_dotenv()
logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("bot")

# Optional comma-separated list of chat ids the bot will answer in. Empty = any chat.
ALLOWED_CHATS = {int(c) for c in os.getenv("ALLOWED_CHAT_IDS", "").replace(" ", "").split(",") if c}
IN_ALLOWED_CHAT = filters.Chat(chat_id=ALLOWED_CHATS) if ALLOWED_CHATS else filters.ALL

# Some apps send PDFs as a generic file type, so also accept them by file name.
PDF_FILES = (filters.Document.PDF | filters.Document.FileExtension("pdf")) & ~filters.UpdateType.EDITED


async def log_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """One log line for everything the bot receives (never the message text),
    so the log shows whether Telegram delivers the group's messages at all."""
    chat, msg = update.effective_chat, update.effective_message
    where = f"chat {chat.id} ({chat.type}{': ' + chat.title if chat.title else ''})" if chat else "no chat"
    if msg and msg.document:
        what = f"file {msg.document.file_name!r} ({msg.document.mime_type})"
    elif msg:
        what = "message"
    else:
        what = "update"
    log.info("Received %s in %s", what, where)


async def on_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "✅ Bot is running. Send an original CAMMED invoice PDF (or reply /discount to one) and I'll reply with the discounted invoice."
    )


async def reply_discounted(msg: Message, asked: bool) -> None:
    """Reply to msg, which carries a PDF, with the discounted invoice.
    asked: someone used /discount, so say why a PDF is skipped instead of staying silent."""
    doc = msg.document
    tg_file = await doc.get_file()
    data = bytes(await tg_file.download_as_bytearray())

    try:
        filename, out = generate(data)
    except NotAnInvoice as e:
        log.info("Skipping %s: not an original invoice (%s)", doc.file_name, e)
        if asked:
            await msg.reply_text(f"ℹ️ {doc.file_name} is not an original invoice ({e}).")
        return
    except InvoiceError as e:
        log.warning("Could not process %s: %s", doc.file_name, e)
        await msg.reply_text(f"⚠️ Could not generate invoice from {doc.file_name}: {e}")
        return

    log.info("Generated %s from %s in chat %s", filename, doc.file_name, msg.chat_id)
    await msg.reply_document(document=io.BytesIO(out), filename=filename)


async def on_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await reply_discounted(update.effective_message, asked=False)


async def on_discount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """/discount sent as a reply to an invoice PDF. Needed for invoices this bot posts itself
    (e.g. from the results system): Telegram never delivers a bot's own messages to it."""
    original = update.effective_message.reply_to_message
    if not original or not original.document:
        await update.effective_message.reply_text("↩️ Reply to an invoice PDF with /discount.")
        return
    await reply_discounted(original, asked=True)


async def on_startup(app: Application) -> None:
    log.info("Logged in as @%s (id %s)", app.bot.username, app.bot.id)


def build_app(token: str) -> Application:
    app = Application.builder().token(token).post_init(on_startup).build()
    app.add_handler(TypeHandler(Update, log_update), group=-1)
    app.add_handler(CommandHandler("start", on_start, filters=IN_ALLOWED_CHAT))
    app.add_handler(CommandHandler("discount", on_discount, filters=IN_ALLOWED_CHAT))
    app.add_handler(MessageHandler(PDF_FILES & IN_ALLOWED_CHAT, on_pdf))
    return app


def main() -> None:
    token = os.environ["BOT_TOKEN"]
    log.info("%d fixed-price tests loaded from %s", len(fixed_items()), fixed_items_source())
    log.info("Answering in %s", f"chats {sorted(ALLOWED_CHATS)}" if ALLOWED_CHATS else "any chat")
    app = build_app(token)
    log.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=False)


if __name__ == "__main__":
    main()
