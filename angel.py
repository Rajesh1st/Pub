import logging
import os
import re
import requests
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("thumbnail_bot_ptb.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")

SETTINGS_MENU, PREFIX_INPUT, SUFFIX_INPUT = range(3)

URL_PATTERN = re.compile(
    r'https?://(?:[a-zA-Z0-9$-_@.&+!*\'(),]|(?:%[0-9a-fA-F]{2}))+'
    r'\.(?:jpg|jpeg|png|webp|bmp)(?:\?.*)?$',
    re.IGNORECASE
)

VIDEO_EXTENSIONS = ("mkv", "mp4", "avi", "mov", "webm", "m4v", "flv")


# -------------------------
# Helper functions
# -------------------------
def insert_suffix_before_extension(filename: str, suffix_text: str) -> str:
    if not suffix_text:
        return filename
    m = re.search(r'\.([A-Za-z0-9]{1,5})$', filename)
    if m:
        ext = m.group(1)
        if ext.lower() in VIDEO_EXTENSIONS:
            base = filename[:m.start()]
            return f"{base} {suffix_text}.{ext}"
    return f"{filename} {suffix_text}"


def escape_html(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def apply_style_to_text(text: str, style: str) -> str:
    if not text:
        return text
    if style == "blockquote":
        lines = text.splitlines()
        quoted = "\n".join("› " + ln for ln in lines)
        return f"<i>{escape_html(quoted)}</i>"
    if style == "pre":
        return f"<pre>{escape_html(text)}</pre>"
    if style == "bold":
        return f"<b>{escape_html(text)}</b>"
    if style == "italic":
        return f"<i>{escape_html(text)}</i>"
    if style == "monospace":
        return f"<code>{escape_html(text)}</code>"
    if style == "underline":
        return f"<u>{escape_html(text)}</u>"
    if style == "strikethrough":
        return f"<s>{escape_html(text)}</s>"
    if style == "spoiler":
        return f"<tg-spoiler>{escape_html(text)}</tg-spoiler>"
    return escape_html(text)


def build_settings_page(user_data: dict, page: int = 1) -> (str, InlineKeyboardMarkup):
    user_id = user_data.get("_id_placeholder", "You")
    caption_style = user_data.get("caption_style", "none")
    prefix = user_data.get("prefix", "")
    suffix = user_data.get("suffix", "")
    mention_on = user_data.get("mention_enabled", True)
    link_wrap = user_data.get("link_wrap", None)

    if page == 1:
        text = f"""
⚙️ <b>Settings — Page 1 / 3</b>

<b>Current style:</b> <code>{caption_style}</code>
<b>Prefix:</b> <code>{prefix or '-'}</code>
<b>Suffix:</b> <code>{suffix or '-'}</code>
<b>Link wrap:</b> <code>{link_wrap or '-'}</code>
<b>Mention (two newlines):</b> <code>{'On' if mention_on else 'Off'}</code>

<b>Choose a basic caption style:</b>
"""
        keyboard = [
            [InlineKeyboardButton("𝐁𝐨𝐥𝐝", callback_data="style:bold"),
             InlineKeyboardButton("𝘐𝘵𝘢𝘭𝘪𝘤", callback_data="style:italic")],
            [InlineKeyboardButton("𝙼𝚘𝚗𝚘𝚜𝚙𝚊𝚌𝚎", callback_data="style:monospace"),
             InlineKeyboardButton("Underline", callback_data="style:underline")],
            [InlineKeyboardButton("Strikethrough", callback_data="style:strikethrough"),
             InlineKeyboardButton("Spoiler", callback_data="style:spoiler")],
            [InlineKeyboardButton("Next ➡️", callback_data="nav:page2"),
             InlineKeyboardButton("🗑 Clear Style", callback_data="style:none")],
            [InlineKeyboardButton("✅ Done", callback_data="style:done")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    elif page == 2:
        text = f"""
⚙️ <b>Settings — Page 2 / 3</b>

<b>Extra formats:</b>
"""
        keyboard = [
            [InlineKeyboardButton("❝ Blockquote", callback_data="style:blockquote"),
             InlineKeyboardButton("⤷ Pre (code block)", callback_data="style:pre")],
            [InlineKeyboardButton("⬅️ Back", callback_data="nav:page1"),
             InlineKeyboardButton("Next ➡️", callback_data="nav:page3")],
            [InlineKeyboardButton("✅ Done", callback_data="style:done")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    else:
        text = f"""
⚙️ <b>Settings — Page 3 / 3</b>

<b>Prefix:</b> <code>{prefix or '-'}</code>
<b>Suffix:</b> <code>{suffix or '-'}</code>
<b>Link wrap:</b> <code>{link_wrap or '-'}</code>
<b>Mention (two newlines):</b> <code>{'On' if mention_on else 'Off'}</code>
"""
        keyboard = [
            [InlineKeyboardButton("Set Prefix", callback_data="set:prefix"),
             InlineKeyboardButton("Set Suffix", callback_data="set:suffix")],
            [InlineKeyboardButton("Set Link Wrap", callback_data="set:link"),
             InlineKeyboardButton("🪄 Preview Caption", callback_data="action:preview")],
            [InlineKeyboardButton("Toggle Mention", callback_data="toggle:mention")],
            [InlineKeyboardButton("⬅️ Back", callback_data="nav:page2"),
             InlineKeyboardButton("✅ Done", callback_data="style:done")]
        ]
        return text, InlineKeyboardMarkup(keyboard)


# -------------------------
# Commands
# -------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = """
🤖 <b>Thumbnail Cover Changer Bot</b>

I can change video thumbnails/covers and style captions.

<b>Commands:</b>
/start - Show help
/settings - Configure caption styles, prefix/suffix/link
/thumb - View saved thumbnail
/clear - Clear thumbnail
/clear_prefix - Remove saved prefix
/clear_suffix - Remove saved suffix
/clear_all - Remove both prefix and suffix
/set_link <url> - Wrap caption with clickable link
/clear_link - Remove link wrapping
"""
    await update.message.reply_text(text, parse_mode='HTML')


# --- new quick clear commands ---
async def clear_prefix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("prefix", None)
    await update.message.reply_text("✅ Prefix cleared successfully!")


async def clear_suffix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("suffix", None)
    await update.message.reply_text("✅ Suffix cleared successfully!")


async def clear_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("prefix", None)
    context.user_data.pop("suffix", None)
    await update.message.reply_text("✅ Prefix & Suffix cleared successfully!")


# --- new link wrap commands ---
async def set_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("❌ Usage: /set_link <url>")
        return
    url = args[0]
    context.user_data["link_wrap"] = url
    await update.message.reply_text(f"✅ Link wrapping enabled:\n<code>{escape_html(url)}</code>", parse_mode='HTML')


async def clear_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("link_wrap", None)
    await update.message.reply_text("✅ Link wrapping disabled.")


# -------------------------
# Settings Handlers
# -------------------------
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ud = context.user_data
    ud.setdefault('caption_style', 'none')
    ud.setdefault('prefix', '')
    ud.setdefault('suffix', '')
    ud.setdefault('mention_enabled', True)
    ud.setdefault('link_wrap', None)

    text, markup = build_settings_page(ud, page=1)
    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU


async def settings_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""
    user_data = context.user_data

    if data.startswith("nav:"):
        page = data.split(":", 1)[1]
        text, markup = build_settings_page(user_data, page=int(page[-1]))
        await query.edit_message_text(text, reply_markup=markup, parse_mode='HTML')
        return SETTINGS_MENU

    if data.startswith("style:"):
        style = data.split(":", 1)[1]
        if style == "done":
            await query.edit_message_text("✅ <b>Settings saved!</b>", parse_mode='HTML')
            return ConversationHandler.END
        user_data['caption_style'] = style
        text, markup = build_settings_page(user_data, page=1)
        await query.edit_message_text(f"✅ Style set to <code>{style}</code>\n\n{text}",
                                      reply_markup=markup, parse_mode='HTML')
        return SETTINGS_MENU

    if data.startswith("set:"):
        which = data.split(":", 1)[1]
        if which == "prefix":
            await query.edit_message_text("✏️ Send your new Prefix text.")
            return PREFIX_INPUT
        elif which == "suffix":
            await query.edit_message_text("✏️ Send your new Suffix text.")
            return SUFFIX_INPUT
        elif which == "link":
            await query.edit_message_text("✏️ Send a valid URL to wrap your captions (send /cancel to abort).")
            return PREFIX_INPUT  # reuse prefix state temporarily

    if data.startswith("toggle:mention"):
        user_data['mention_enabled'] = not user_data.get('mention_enabled', True)
        text, markup = build_settings_page(user_data, page=3)
        await query.edit_message_text(text, reply_markup=markup, parse_mode='HTML')
        return SETTINGS_MENU

    if data.startswith("action:preview"):
        sample = "🔥 Sample Movie [1080p]"
        prefix = user_data.get('prefix', '')
        suffix = user_data.get('suffix', '')
        style = user_data.get('caption_style', 'none')
        composed = f"{prefix} {sample}".strip()
        composed = insert_suffix_before_extension(composed, suffix)
        styled = apply_style_to_text(composed, style)
        if user_data.get('link_wrap'):
            styled = f'<a href="{escape_html(user_data["link_wrap"])}">{styled}</a>'
        await query.message.reply_text(f"🪄 <b>Preview:</b>\n{styled}", parse_mode='HTML')
        return SETTINGS_MENU

    if data == "style:none":
        user_data['caption_style'] = 'none'
        text, markup = build_settings_page(user_data, page=1)
        await query.edit_message_text("✅ Style cleared.\n\n" + text, reply_markup=markup, parse_mode='HTML')
        return SETTINGS_MENU

    return SETTINGS_MENU


async def prefix_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['prefix'] = update.message.text.strip()
    await update.message.reply_text("✅ Prefix updated.")
    text, markup = build_settings_page(context.user_data, page=3)
    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU


async def suffix_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['suffix'] = update.message.text.strip()
    await update.message.reply_text("✅ Suffix updated.")
    text, markup = build_settings_page(context.user_data, page=3)
    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')
    return SETTINGS_MENU


async def cancel_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Settings menu closed.")
    return ConversationHandler.END


# -------------------------
# Thumbnail / Video handlers
# -------------------------
async def view_thumb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thumb_file_id = context.user_data.get("thumb_file_id")
    if thumb_file_id:
        await update.message.reply_photo(thumb_file_id, caption="📷 Your current thumbnail", parse_mode='HTML')
    else:
        await update.message.reply_text("📷 No thumbnail saved.")


async def clear_thumb_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("thumb_file_id", None)
    await update.message.reply_text("✅ Thumbnail cleared.")


async def save_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["thumb_file_id"] = update.message.photo[-1].file_id
    await update.message.reply_text("✅ Thumbnail saved!")


async def handle_url_thumb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    if URL_PATTERN.match(url):
        try:
            res = requests.get(url, timeout=10)
            res.raise_for_status()
            msg = await update.message.reply_photo(photo=res.content, caption="🖼️ Image fetched.")
            context.user_data["thumb_file_id"] = msg.photo[-1].file_id
            await update.message.reply_text("✅ Thumbnail saved from URL!")
        except Exception as e:
            await update.message.reply_text("❌ Failed to download image.")
    return


async def send_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thumb = context.user_data.get("thumb_file_id")
    if not thumb:
        await update.message.reply_text("⚠️ Please send a thumbnail first.")
        return

    video_file_id = update.message.video.file_id if update.message.video else update.message.document.file_id
    ud = context.user_data
    prefix, suffix = ud.get('prefix', ''), ud.get('suffix', '')
    caption_style, mention_enabled = ud.get('caption_style', 'none'), ud.get('mention_enabled', True)
    link_wrap = ud.get('link_wrap', None)

    caption = update.message.caption or ""
    main_caption, mention_text = caption, ""
    if "\n\n" in caption:
        parts = caption.split("\n\n", 1)
        main_caption, mention_text = parts[0], parts[1] if mention_enabled else ""

    composed = f"{prefix} {main_caption}".strip()
    composed = insert_suffix_before_extension(composed, suffix)
    if mention_text:
        composed += f"\n\n{mention_text}"

    final_caption = apply_style_to_text(composed, caption_style)
    if link_wrap:
        final_caption = f'<a href="{escape_html(link_wrap)}">{final_caption}</a>'

    await context.bot.send_video(
        chat_id=update.message.chat_id,
        video=video_file_id,
        caption=final_caption,
        cover=thumb,
        parse_mode='HTML'
    )


# -------------------------
# Main
# -------------------------
def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN missing.")
        return

    app = Application.builder().token(BOT_TOKEN).build()

    settings_conv = ConversationHandler(
        entry_points=[CommandHandler("settings", settings_command)],
        states={
            SETTINGS_MENU: [CallbackQueryHandler(settings_button_handler)],
            PREFIX_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, prefix_input_handler)],
            SUFFIX_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, suffix_input_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel_settings)],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("thumb", view_thumb_command))
    app.add_handler(CommandHandler("clear", clear_thumb_command))
    app.add_handler(settings_conv)

    # New feature handlers
    app.add_handler(CommandHandler("clear_prefix", clear_prefix_command))
    app.add_handler(CommandHandler("clear_suffix", clear_suffix_command))
    app.add_handler(CommandHandler("clear_all", clear_all_command))
    app.add_handler(CommandHandler("set_link", set_link_command))
    app.add_handler(CommandHandler("clear_link", clear_link_command))

    app.add_handler(MessageHandler(filters.PHOTO, save_thumb))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url_thumb))
    app.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, send_video))

    logger.info("Starting Thumbnail Cover Changer Bot...")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
