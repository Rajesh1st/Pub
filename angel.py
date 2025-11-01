import logging
import os
import re
import requests
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    ChatPermissions,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
    ConversationHandler,
)
from typing import Tuple, List

# -------------------------
# Setup
# -------------------------
load_dotenv()

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

# Conversation states
SETTINGS_MENU, PREFIX_INPUT, SUFFIX_INPUT, LINK_INPUT, MENTION_INPUT, \
REPLACE_INPUT, REMOVE_INPUT, DUMP_WAIT_FORWARD, BUTTON_TEXT_INPUT, BUTTON_URL_INPUT = range(10)

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


def apply_style_to_text(text: str, styles) -> str:
    \"\"\"Apply multiple styles. styles can be a string or list/tuple/set of strings.\"\"\"
    if not text:
        return text
    if not styles or styles == 'none':
        return escape_html(text)
    if isinstance(styles, str):
        styles = [styles]
    styled = escape_html(text)
    # apply block-level styles last (blockquote, pre)
    atomic = []
    block = None
    for s in styles:
        if s in ('blockquote', 'pre'):
            block = s
        else:
            atomic.append(s)
    for s in atomic:
        if s == "bold":
            styled = f"<b>{styled}</b>"
        elif s == "italic":
            styled = f"<i>{styled}</i>"
        elif s == "monospace":
            styled = f"<code>{styled}</code>"
        elif s == "underline":
            styled = f"<u>{styled}</u>"
        elif s == "strikethrough":
            styled = f"<s>{styled}</s>"
        elif s == "spoiler":
            styled = f"<tg-spoiler>{styled}</tg-spoiler>"
    if block == 'blockquote':
        styled = f"<blockquote>{styled}</blockquote>"
    if block == 'pre':
        styled = f"<pre>{styled}</pre>"
    return styled


def remove_words_from_text(text: str, words: List[str]) -> str:
    if not words:
        return text
    # Remove whole words (case-insensitive) and also these tokens in mid text
    pattern = r'(' + '|'.join(re.escape(w.strip()) for w in words if w.strip()) + r')'
    if not pattern or pattern == r'()':
        return text
    return re.sub(pattern, '', text, flags=re.IGNORECASE).strip()


def apply_replacements(text: str, replacements: List[Tuple[str, str]]) -> str:
    out = text
    for old, new in replacements:
        if not old:
            continue
        out = re.sub(re.escape(old), new, out, flags=re.IGNORECASE)
    return out


def remove_links_and_usernames(text: str, remove_links: bool, remove_usernames: bool) -> str:
    out = text
    if remove_links:
        # remove http/s and t.me and telegram.me and www links
        out = re.sub(r'(https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+)', '', out, flags=re.IGNORECASE)
    if remove_usernames:
        # remove @username tokens
        out = re.sub(r'@\w+', '', out)
    return out.strip()


def remove_mkv_tail(text: str) -> str:
    # remove .mkv and everything after it on that line
    return re.sub(r'\.mkv.*', '', text, flags=re.IGNORECASE)


def ensure_list(v):
    if not v:
        return []
    if isinstance(v, (list, tuple, set)):
        return list(v)
    return [v]


# -------------------------
# Build Settings Pages (multi-page with toggles)
# -------------------------
def build_settings_page(user_data: dict, page: int = 1) -> (str, InlineKeyboardMarkup):
    caption_styles = ensure_list(user_data.get("caption_style", []))
    prefix = user_data.get("prefix", "")
    suffix = user_data.get("suffix", "")
    mention_text = user_data.get("mention_text", "")
    link_wrap = user_data.get("link_wrap", "")
    replacements = user_data.get("replacements", [])
    removes = user_data.get("remove_words", [])
    auto_links = user_data.get("auto_remove_links", False)
    auto_user = user_data.get("auto_remove_usernames", False)
    auto_mkv = user_data.get("auto_remove_mkv_tail", False)
    dump_channel = user_data.get("dump_channel_id", None)
    attach_button = user_data.get("attach_button", False)
    button_text = user_data.get("button_text", "")
    button_url = user_data.get("button_url", "")

    if page == 1:
        text = f\"\"\"\n⚙️ <b>Settings — Page 1 / 3</b>\n\n<b>Current styles:</b> <code>{', '.join(caption_styles) or 'none'}</code>\n<b>Prefix:</b> <code>{prefix or '-'}</code>\n<b>Suffix:</b> <code>{suffix or '-'}</code>\n\n<b>Choose styles (toggle any):</b>\n\"\"\"
        keyboard = [
            [InlineKeyboardButton("𝐁𝐨𝐥𝐝", callback_data="toggle_style:bold"),
             InlineKeyboardButton("𝘐𝘵𝘢𝘭𝘪𝘤", callback_data="toggle_style:italic")],
            [InlineKeyboardButton("𝙼𝚘𝚗𝚘", callback_data="toggle_style:monospace"),
             InlineKeyboardButton("Underline", callback_data="toggle_style:underline")],
            [InlineKeyboardButton("Strikethrough", callback_data="toggle_style:strikethrough"),
             InlineKeyboardButton("Spoiler", callback_data="toggle_style:spoiler")],
            [InlineKeyboardButton("❝ Blockquote", callback_data="toggle_style:blockquote"),
             InlineKeyboardButton("⤷ Pre (code)", callback_data="toggle_style:pre")],
            [InlineKeyboardButton("Next ➡️", callback_data="nav:page2"),
             InlineKeyboardButton("🗑 Clear Styles", callback_data="style:none")],
            [InlineKeyboardButton("✅ Done", callback_data="style:done")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    elif page == 2:
        text = f\"\"\"\n⚙️ <b>Settings — Page 2 / 3</b>\n\n<b>Prefix:</b> <code>{prefix or '-'}</code>\n<b>Suffix:</b> <code>{suffix or '-'}</code>\n\n\"\"\"
        keyboard = [
            [InlineKeyboardButton("Set Prefix", callback_data="set:prefix"),
             InlineKeyboardButton("Set Suffix", callback_data="set:suffix")],
            [InlineKeyboardButton("Set Link Wrap", callback_data="set:link") ,
             InlineKeyboardButton("Set Mention", callback_data="set:mention")],
            [InlineKeyboardButton("Replace words", callback_data="set:replace"),
             InlineKeyboardButton("Remove words", callback_data="set:remove")],
            [InlineKeyboardButton("⬅️ Back", callback_data="nav:page1"),
             InlineKeyboardButton("Next ➡️", callback_data="nav:page3")],
            [InlineKeyboardButton("✅ Done", callback_data="style:done")]
        ]
        return text, InlineKeyboardMarkup(keyboard)

    else:
        text = f\"\"\"\n⚙️ <b>Settings — Page 3 / 3</b>\n\n<b>Auto remove links:</b> <code>{'ON' if auto_links else 'OFF'}</code>\n<b>Auto remove usernames:</b> <code>{'ON' if auto_user else 'OFF'}</code>\n<b>Auto remove .mkv tail:</b> <code>{'ON' if auto_mkv else 'OFF'}</code>\n<b>Dump channel:</b> <code>{dump_channel or '-'}</code>\n<b>Attach button to videos:</b> <code>{'ON' if attach_button else 'OFF'}</code>\n<b>Button:</b> <code>{button_text or '-'} -> {button_url or '-'}</code>\n\"\"\"
        keyboard = [
            [InlineKeyboardButton("Toggle Auto Link Remove", callback_data="toggle:auto_links"),
             InlineKeyboardButton("Toggle Auto Username Remove", callback_data="toggle:auto_user")],
            [InlineKeyboardButton("Toggle Auto .mkv remove", callback_data="toggle:auto_mkv"),
             InlineKeyboardButton("Set Dump Channel", callback_data="set:dump")],
            [InlineKeyboardButton("Toggle Attach Button", callback_data="toggle:attach_button"),
             InlineKeyboardButton("Set Button Text", callback_data="set:button_text")],
            [InlineKeyboardButton("Set Button URL", callback_data="set:button_url"),
             InlineKeyboardButton("🧹 Clear All Settings", callback_data="confirm:clear_all")],
            [InlineKeyboardButton("🪄 Preview Caption", callback_data="action:preview")],
            [InlineKeyboardButton("⬅️ Back", callback_data="nav:page2"),
             InlineKeyboardButton("✅ Done", callback_data="style:done")]
        ]
        return text, InlineKeyboardMarkup(keyboard)


# -------------------------
# Commands
# -------------------------
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = \"\"\"\n🤖 <b>Thumbnail Cover Changer Bot — Enhanced</b>\n\nI can change video thumbnails/covers and style captions with many options.\n\n<b>Commands:</b>\n/start - Show help\n/settings - Configure caption styles, prefix/suffix/link and advanced options\n/thumb - View saved thumbnail\n/clear - Clear thumbnail\n/replace - Set text replacements (old - new, comma separated)\n/remove_words - Set words to remove (comma separated)\n/dump_clear - Clear dump channel\n/clear_everything - 🧹 Clear all saved settings at once\n\"\"\"\n    await update.message.reply_text(text, parse_mode='HTML')\n\n\nasync def clear_prefix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    context.user_data.pop(\"prefix\", None)\n    await update.message.reply_text(\"✅ Prefix cleared!\")\n\n\nasync def clear_suffix_command(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    context.user_data.pop(\"suffix\", None)\n    await update.message.reply_text(\"✅ Suffix cleared!\")\n\n\nasync def clear_link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    context.user_data.pop(\"link_wrap\", None)\n    await update.message.reply_text(\"✅ Link wrap cleared!\")\n\n\nasync def clear_mention_command(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    context.user_data.pop(\"mention_text\", None)\n    await update.message.reply_text(\"✅ Mention text cleared!\")\n\n\nasync def clear_everything_command(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    for k in [\"prefix\", \"suffix\", \"mention_text\", \"link_wrap\", \"caption_style\", \"replacements\", \"remove_words\", \"auto_remove_links\", \"auto_remove_usernames\", \"auto_remove_mkv_tail\", \"dump_channel_id\", \"attach_button\", \"button_text\", \"button_url\"]:\n        context.user_data.pop(k, None)\n    await update.message.reply_text(\"🧹 All settings cleared!\")\n\n\nasync def dump_clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    context.user_data.pop(\"dump_channel_id\", None)\n    await update.message.reply_text(\"✅ Dump channel cleared.\")\n\n\n# -------------------------\n# Settings Handler\n# -------------------------\nasync def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    ud = context.user_data\n    ud.setdefault('caption_style', [])\n    ud.setdefault('prefix', '')\n    ud.setdefault('suffix', '')\n    ud.setdefault('mention_text', '')\n    ud.setdefault('link_wrap', '')\n    ud.setdefault('replacements', [])\n    ud.setdefault('remove_words', [])\n    ud.setdefault('auto_remove_links', False)\n    ud.setdefault('auto_remove_usernames', False)\n    ud.setdefault('auto_remove_mkv_tail', False)\n    ud.setdefault('dump_channel_id', None)\n    ud.setdefault('attach_button', False)\n    ud.setdefault('button_text', '')\n    ud.setdefault('button_url', '')\n\n    text, markup = build_settings_page(ud, page=1)\n    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')\n    return SETTINGS_MENU\n\n\nasync def settings_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    query = update.callback_query\n    await query.answer()\n    data = query.data or \"\"\n    ud = context.user_data\n\n    # Navigation\n    if data.startswith(\"nav:\"):\n        page = int(data.split(':',1)[1])\n        text, markup = build_settings_page(ud, page=page)\n        await query.edit_message_text(text, reply_markup=markup, parse_mode='HTML')\n        return SETTINGS_MENU\n\n    # Toggle style (multi-select)\n    if data.startswith(\"toggle_style:\"):\n        style = data.split(':',1)[1]\n        styles = set(ensure_list(ud.get('caption_style', [])))\n        if style in styles:\n            styles.remove(style)\n        else:\n            styles.add(style)\n        ud['caption_style'] = list(styles)\n        text, markup = build_settings_page(ud, page=1)\n        await query.edit_message_text(f\"✅ Styles updated.\\n\\n{text}\", reply_markup=markup, parse_mode='HTML')\n        return SETTINGS_MENU\n\n    # Style set/clear\n    if data.startswith(\"style:\"):\n        style = data.split(\":\",1)[1]\n        if style == 'done':\n            await query.edit_message_text(\"✅ <b>Settings saved!</b>\", parse_mode='HTML')\n            return ConversationHandler.END\n        if style == 'none':\n            ud['caption_style'] = []\n            text, markup = build_settings_page(ud, page=1)\n            await query.edit_message_text(f\"✅ Styles cleared.\\n\\n{text}\", reply_markup=markup, parse_mode='HTML')\n            return SETTINGS_MENU\n\n    # Set inputs\n    if data.startswith(\"set:\"):\n        which = data.split(\":\",1)[1]\n        prompts = {\n            \"prefix\": \"✏️ Send your new Prefix text.\",\n            \"suffix\": \"✏️ Send your new Suffix text.\",\n            \"link\": \"🔗 Send the URL to wrap your captions.\",\n            \"mention\": \"💬 Send your custom Mention text (like 'Join my channel - @fjiffyuv').\",\n            \"replace\": \"✏️ Send replacements in format: old - new, old2 - new2\",\n            \"remove\": \"✏️ Send comma-separated words to remove (e.g. hd, 2025, Hindi)\",\n            \"dump\": \"➡️ Please forward any message FROM your CHANNEL to me now (I will detect channel and save it).\",\n            \"button_text\": \"✏️ Send default Button Text (will be attached under videos if enabled).\",\n            \"button_url\": \"🔗 Send default Button URL (for the button).\",\n        }\n        await query.edit_message_text(prompts[which])\n        if which == 'prefix':\n            return PREFIX_INPUT\n        if which == 'suffix':\n            return SUFFIX_INPUT\n        if which == 'link':\n            return LINK_INPUT\n        if which == 'mention':\n            return MENTION_INPUT\n        if which == 'replace':\n            return REPLACE_INPUT\n        if which == 'remove':\n            return REMOVE_INPUT\n        if which == 'dump':\n            return DUMP_WAIT_FORWARD\n        if which == 'button_text':\n            return BUTTON_TEXT_INPUT\n        if which == 'button_url':\n            return BUTTON_URL_INPUT\n\n    # Toggles in page 3\n    if data.startswith(\"toggle:\"):\n        thing = data.split(\":\",1)[1]\n        if thing == 'auto_links':\n            ud['auto_remove_links'] = not ud.get('auto_remove_links', False)\n        elif thing == 'auto_user':\n            ud['auto_remove_usernames'] = not ud.get('auto_remove_usernames', False)\n        elif thing == 'auto_mkv':\n            ud['auto_remove_mkv_tail'] = not ud.get('auto_remove_mkv_tail', False)\n        elif thing == 'attach_button':\n            ud['attach_button'] = not ud.get('attach_button', False)\n        text, markup = build_settings_page(ud, page=3)\n        await query.edit_message_text(text, reply_markup=markup, parse_mode='HTML')\n        return SETTINGS_MENU\n\n    # Clear all confirm\n    if data == 'confirm:clear_all':\n        keyboard = [[InlineKeyboardButton(\"✅ Yes, Clear All\", callback_data=\"clear:all\"),\n                     InlineKeyboardButton(\"❌ No, Cancel\", callback_data=\"cancel:clear_all\")]]\n        await query.edit_message_text(\"⚠️ Are you sure you want to clear all saved settings?\", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')\n        return SETTINGS_MENU\n\n    if data == 'clear:all':\n        for key in [\"prefix\", \"suffix\", \"mention_text\", \"link_wrap\", \"caption_style\", \"replacements\", \"remove_words\", \"auto_remove_links\", \"auto_remove_usernames\", \"auto_remove_mkv_tail\", \"dump_channel_id\", \"attach_button\", \"button_text\", \"button_url\"]:\n            ud.pop(key, None)\n        text, markup = build_settings_page(ud, page=3)\n        await query.edit_message_text(\"🧹 All settings cleared!\\n\\n\" + text, reply_markup=markup, parse_mode='HTML')\n        return SETTINGS_MENU\n\n    if data == 'cancel:clear_all':\n        text, markup = build_settings_page(ud, page=3)\n        await query.edit_message_text(\"❌ Clear all cancelled.\\n\\n\" + text, reply_markup=markup, parse_mode='HTML')\n        return SETTINGS_MENU\n\n    # Preview\n    if data.startswith(\"action:preview\"):\n        sample = \"🔥 The Summer Hikaru Died S01 Ep 07 - 12 [Hindi-English-Japanese] 1080p HEVC 10bit WEB-DL ESub ~ Aᴍɪᴛ ~ [TW4ALL].mkv\"\n        prefix = ud.get('prefix', '')\n        suffix = ud.get('suffix', '')\n        styles = ud.get('caption_style', [])\n        mention_text = ud.get('mention_text', '')\n        link_wrap = ud.get('link_wrap', '')\n        composed = f\"{prefix} {sample}\".strip()\n        composed = insert_suffix_before_extension(composed, suffix)\n        if mention_text:\n            composed += f\"\\n\\n{mention_text}\"\n        if ud.get('auto_remove_links'):\n            composed = remove_links_and_usernames(composed, True, False)\n        if ud.get('auto_remove_usernames'):\n            composed = remove_links_and_usernames(composed, False, True)\n        if ud.get('auto_remove_mkv_tail'):\n            composed = remove_mkv_tail(composed)\n        # apply replacements and removals\n        composed = apply_replacements(composed, ud.get('replacements', []))\n        composed = remove_words_from_text(composed, ud.get('remove_words', []))\n        styled = apply_style_to_text(composed, styles)\n        if link_wrap:\n            styled = f'<a href=\"{escape_html(link_wrap)}\">{styled}</a>'\n        await query.message.reply_text(f\"🪄 <b>Preview:</b>\\n{styled}\", parse_mode='HTML')\n        return SETTINGS_MENU\n\n    return SETTINGS_MENU\n\n\n# -------------------------\n# Input Handlers\n# -------------------------\nasync def prefix_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    context.user_data['prefix'] = update.message.text.strip()\n    await update.message.reply_text(\"✅ Prefix updated.\")\n    text, markup = build_settings_page(context.user_data, page=2)\n    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')\n    return SETTINGS_MENU\n\n\nasync def suffix_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    context.user_data['suffix'] = update.message.text.strip()\n    await update.message.reply_text(\"✅ Suffix updated.\")\n    text, markup = build_settings_page(context.user_data, page=2)\n    await update.message.reply_text(text, reply_markup=markup, parse_mode='HTML')\n    return SETTINGS_MENU\n\n\nasync def link_input_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):\n    context.user_data['link_wrap'] = update.message.text.strip()\n    await update.message.reply_text(\"✅ Link wrap URL saved!\")\n    text, markup = build_settings_page(context.user_data, page=2)\n    await up
