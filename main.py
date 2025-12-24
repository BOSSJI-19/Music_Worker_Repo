import asyncio
import os
from threading import Thread
from flask import Flask
from pyrogram import Client, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pytgcalls import PyTgCalls

# ✅ LEGACY IMPORTS (py-tgcalls 0.9.7)
from pytgcalls.types.input_stream import InputStream
from pytgcalls.types.input_stream.quality import HighQualityAudio

from pymongo import MongoClient
from config import API_ID, API_HASH, SESSION, MONGO_URL, LOGGER_ID, SUPPORT_GC
from youtube import download_song

# --- FLASK SETUP ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "🎵 Music Worker is Alive & Running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

def keep_alive():
    Thread(target=run_web).start()

# --- CLIENT SETUP ---
app = Client(
    "MusicWorker",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION,
    plugins=dict(root="plugins")
)
call_py = PyTgCalls(app)

# --- DATABASE ---
mongo = MongoClient(MONGO_URL)
db = mongo["Music_Database"]
queue_col = db["Music_Queue"]

# --- BUTTONS ---
def music_buttons():
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏹ Stop", callback_data="music_stop"),
                InlineKeyboardButton("⏭ Skip", callback_data="music_skip")
            ],
            [
                InlineKeyboardButton("🆘 Support", url=SUPPORT_GC),
                InlineKeyboardButton("❌ Close", callback_data="music_close")
            ]
        ]
    )

# --- STARTUP LOGGER ---
async def send_startup_log():
    try:
        me = await app.get_me()
        cookie_status = "✅ Found" if os.path.exists("cookies.txt") else "❌ Missing"

        await app.send_message(
            LOGGER_ID,
            f"""
<b>🎹 Music Worker Online</b>

👤 {me.mention}
🆔 <code>{me.id}</code>
🍪 Cookies: {cookie_status}
⚙️ PyTgCalls: v0.9.7
"""
        )
    except Exception as e:
        print(f"Logger Error: {e}")

# --- MUSIC LOGIC ---
async def process_task(task):
    chat_id = int(task["chat_id"])
    link = task["link"]
    query = task["song"]
    requester = task.get("requester", "Unknown")

    # JOIN
    try:
        await app.get_chat_member(chat_id, "me")
    except:
        try:
            await app.join_chat(link)
            await asyncio.sleep(2)
        except:
            queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "failed"}})
            return

    # DOWNLOAD
    file_path, title = await download_song(query, chat_id)
    if not file_path:
        queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "failed"}})
        return

    # PLAY
    try:
        await call_py.join_group_call(
            chat_id,
            InputStream(file_path, HighQualityAudio())
        )

        queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "playing"}})

        # 🔔 GROUP MESSAGE
        await app.send_message(
            chat_id,
            f"""
🎶 <b>Now Playing</b>

🎧 <b>Title :</b> {title}
👤 <b>Request By :</b> {requester}
""",
            reply_markup=music_buttons()
        )

        # 🧾 LOGGER MESSAGE
        await app.send_message(
            LOGGER_ID,
            f"▶️ Playing in <code>{chat_id}</code>\n🎧 {title}\n👤 {requester}"
        )

    except Exception as e:
        print(f"Play Error: {e}")
        queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "error"}})

# --- CALLBACK HANDLER ---
@app.on_callback_query()
async def music_controls(_, query):
    data = query.data
    chat_id = query.message.chat.id

    if data == "music_stop":
        await call_py.leave_group_call(chat_id)
        await query.message.edit_text("⏹ <b>Music Stopped</b>")

    elif data == "music_skip":
        queue_col.update_many(
            {"chat_id": chat_id, "status": "pending"},
            {"$set": {"status": "skipped"}}
        )
        await query.message.edit_text("⏭ <b>Skipped to Next Track</b>")

    elif data == "music_close":
        await query.message.delete()

# --- LOOP ---
async def music_monitor():
    while True:
        task = queue_col.find_one_and_update(
            {"status": "pending"},
            {"$set": {"status": "processing"}}
        )
        if task:
            await process_task(task)
        await asyncio.sleep(3)

# --- RUN ---
async def main():
    await app.start()
    await call_py.start()
    await send_startup_log()
    asyncio.create_task(music_monitor())
    await idle()

if __name__ == "__main__":
    keep_alive()
    asyncio.get_event_loop().run_until_complete(main())
