import asyncio
import os
from pyrogram import Client, idle
from pytgcalls import PyTgCalls
from pytgcalls.types import InputAudioStream  # <--- OLD SYNTAX
from pytgcalls.types import AudioQuality
from pymongo import MongoClient
from config import API_ID, API_HASH, SESSION, MONGO_URL, LOGGER_ID
from youtube import download_song

# --- CLIENT SETUP ---
app = Client(
    "MusicWorker",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION,
    plugins=dict(root="plugins") # Plugins folder load karega
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
        txt = f"🎵 **Legacy Music System Active**\n🤖 Assistant: {me.mention}\n⚙️ Version: 0.9.7"
        await app.send_message(LOGGER_ID, txt)
    except: pass

# --- MUSIC LOGIC ---
async def process_task(task):
    chat_id = task["chat_id"]
    link = task["link"]
    query = task["song"]

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

    # 4. PLAY (LEGACY STYLE)
    try:
        # 0.9.7 mein play() nahi hota, join_group_call() hota hai
        await call_py.join_group_call(
            int(chat_id),
            InputAudioStream(
                file_path,
            )
        )
        queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "playing"}})
        await app.send_message(LOGGER_ID, f"▶️ **Playing:** {title}")
        
    except Exception as e:
        # Agar already joined hai, toh stream change karo
        try:
            await call_py.change_stream(
                int(chat_id),
                InputAudioStream(
                    file_path,
                )
            )
            queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "playing"}})
        except:
            print(f"Play Error: {e}")
            queue_col.update_one({"_id": task["_id"]}, {"$set": {"status": "error"}})

# --- LOOP ---
async def music_monitor():
    print("👀 Legacy Monitor Started...")
    while True:
        # Pending tasks dhundo
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
    app.run(main())
  
