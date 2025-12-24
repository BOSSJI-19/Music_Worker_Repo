import asyncio
import os
from threading import Thread
from flask import Flask  # <--- NEW
from pyrogram import Client, idle
from pytgcalls import PyTgCalls
from pytgcalls.types import InputAudioStream
from pytgcalls.types import AudioQuality
from pymongo import MongoClient
from config import API_ID, API_HASH, SESSION, MONGO_URL, LOGGER_ID
from youtube import download_song

# --- FLASK SETUP (FOR 24/7 UPTIME) 🟢 ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "🎵 Music Worker is Alive & Running!"

def run_web():
    # Port Render/Server se uthayega ya default 8080 lega
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = Thread(target=run_web)
    t.start()

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

# --- STARTUP MESSAGE ---
async def send_startup_log():
    try:
        me = await app.get_me()
        
        # Check Cookies File
        if os.path.exists("cookies.txt"):
            cookie_status = "✅ Found (Turbo Mode)"
        else:
            cookie_status = "❌ Missing (Normal Mode)"

        # Stylish Message
        txt = f"""
<b>🎹 Music Worker Online (Legacy)</b>

<b>👤 Assistant:</b> {me.mention}
<b>🆔 ID:</b> <code>{me.id}</code>
<b>🍪 Cookies:</b> {cookie_status}
<b>🌐 Web Server:</b> <code>Online 🟢</code>
<b>⚙️ PyTgCalls:</b> <code>v0.9.7</code>

<i>🚀 Ready to Search, Download & Play!</i>
"""
        await app.send_message(LOGGER_ID, txt)
        print("✅ Startup Log Sent!")
    except Exception as e:
        print(f"❌ Logger Error: {e}")

# --- MUSIC LOGIC ---
async def process_task(task):
    chat_id = task["chat_id"]
    link = task["link"]
    query = task["song"]
    requester = task.get("requester", "Unknown")

    # 1. JOIN CHECK
    try:
        await app.get_chat_member(chat_id, "me")
    except:
        try:
            print(f"Joining {chat_id} via Link...")
            await app.join_chat(link)
            await asyncio.sleep(2)
        except Exception as e:
            print(f"Join Error: {e}")
            queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "failed"}})
            return

    # 2. LOGGING
    try:
        await app.send_message(LOGGER_ID, f"🔍 **Searching:** `{query}`")
    except: pass

    # 3. DOWNLOAD
    file_path, title = await download_song(query, chat_id)
    if not file_path:
        queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "failed"}})
        return

    # 4. PLAY (LEGACY STYLE v0.9.7)
    try:
        await call_py.join_group_call(
            int(chat_id),
            InputAudioStream(file_path)
        )
        
        queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "playing"}})
        await app.send_message(LOGGER_ID, f"▶️ **Playing:** {title}\n👤 **Req:** {requester}")
        
    except Exception as e:
        try:
            await call_py.change_stream(
                int(chat_id),
                InputAudioStream(file_path)
            )
            queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "playing"}})
            await app.send_message(LOGGER_ID, f"▶️ **Track Changed:** {title}")
        except:
            print(f"Play Error: {e}")
            queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "error"}})

# --- LOOP ---
async def music_monitor():
    print("👀 Legacy Monitor Started...")
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
    print("🔵 Starting Client...")
    await app.start()
    
    print("🔵 Starting PyTgCalls...")
    await call_py.start()
    
    # Send Log
    await send_startup_log()
    
    # Monitor Start
    asyncio.create_task(music_monitor())
    
    print("🟢 Bot is Idle and Running!")
    await idle()

if __name__ == "__main__":
    # 🔥 Flask Server Start (Background Thread)
    keep_alive()
    # 🔥 Bot Start
    app.run(main())
    
