import asyncio
import os
from threading import Thread
from flask import Flask
from pyrogram import Client, idle, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import InputStream
from pytgcalls.types.input_stream.quality import HighQualityAudio
from pymongo import MongoClient
from config import API_ID, API_HASH, SESSION, MONGO_URL, LOGGER_ID, SUPPORT_GC
from youtube import download_song

# FLASK SETUP
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "🎵 Music Worker is Alive & Running!"

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port)

def keep_alive():
    Thread(target=run_web).start()

# CLIENT SETUP
app = Client(
    "MusicWorker",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION,
    plugins=dict(root="plugins")
)
call_py = PyTgCalls(app)

# DATABASE
mongo = MongoClient(MONGO_URL)
db = mongo["Music_Database"]
queue_col = db["Music_Queue"]

# GLOBAL VARIABLES
current_playing = {}
is_playing = {}

# BUTTONS
def music_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏹ Stop", callback_data="music_stop"),
            InlineKeyboardButton("⏭ Skip", callback_data="music_skip")
        ],
        [
            InlineKeyboardButton("⏸️ Pause", callback_data="music_pause"),
            InlineKeyboardButton("▶️ Resume", callback_data="music_resume")
        ],
        [
            InlineKeyboardButton("🆘 Support", url=SUPPORT_GC),
            InlineKeyboardButton("❌ Close", callback_data="music_close")
        ]
    ])

# STARTUP LOGGER
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
        print(f"✅ Bot started as @{me.username}")
    except Exception as e:
        print(f"Logger Error: {e}")

# JOIN VC FUNCTION
async def join_voice_chat(chat_id, link=None):
    try:
        # Check if already in group call
        call = await call_py.get_active_call(chat_id)
        if call:
            return True
    except:
        pass
    
    try:
        # Join voice chat
        await call_py.join_group_call(
            chat_id,
            InputStream(
                InputAudioStream(
                    "https://raw.githubusercontent.com/TeamYukki/YukkiMusicBot/main/assets/startup.mp3",
                ),
                HighQualityAudio(),
            ),
        )
        print(f"✅ Joined voice chat: {chat_id}")
        return True
    except Exception as e:
        print(f"❌ Error joining voice chat {chat_id}: {e}")
        # Try to join group first if link provided
        if link:
            try:
                await app.join_chat(link)
                await asyncio.sleep(2)
                return await join_voice_chat(chat_id)
            except Exception as join_error:
                print(f"❌ Can't join group: {join_error}")
        return False

# MUSIC LOGIC
async def process_task(task):
    chat_id = int(task["chat_id"])
    link = task.get("link", "")
    query = task.get("song", "")
    requester = task.get("requester", "Unknown")
    task_id = task["_id"]
    
    print(f"🎵 Processing task for chat {chat_id}: {query}")
    
    # Update status
    queue_col.update_one({"_id": task_id}, {"$set": {"status": "processing"}})
    
    # DOWNLOAD SONG FIRST
    file_path, title = await download_song(query, chat_id)
    if not file_path:
        queue_col.update_one({"_id": task_id}, {"$set": {"status": "failed"}})
        print(f"❌ Download failed for: {query}")
        return
    
    print(f"✅ Downloaded: {title} -> {file_path}")
    
    # JOIN GROUP (if needed)
    try:
        await app.get_chat_member(chat_id, "me")
    except:
        if link:
            try:
                await app.join_chat(link)
                await asyncio.sleep(3)
                print(f"✅ Joined group: {chat_id}")
            except Exception as e:
                print(f"❌ Can't join group: {e}")
                queue_col.update_one({"_id": task_id}, {"$set": {"status": "failed"}})
                return
    
    # JOIN VOICE CHAT
    voice_joined = await join_voice_chat(chat_id, link)
    if not voice_joined:
        queue_col.update_one({"_id": task_id}, {"$set": {"status": "failed"}})
        return
    
    # PLAY MUSIC
    try:
        # Set playing status
        is_playing[chat_id] = True
        current_playing[chat_id] = {
            "title": title,
            "file_path": file_path,
            "requester": requester
        }
        
        # Play the audio
        await call_py.change_stream(
            chat_id,
            InputStream(file_path, HighQualityAudio())
        )
        
        # Update database
        queue_col.update_one({"_id": task_id}, {"$set": {"status": "playing"}})
        
        print(f"🎶 Now playing in {chat_id}: {title}")
        
        # Send playing message
        await app.send_message(
            chat_id,
            f"""
🎶 <b>Now Playing</b>

🎧 <b>Title :</b> {title}
👤 <b>Request By :</b> {requester}
⚙️ <b>Status :</b> Playing...
""",
            reply_markup=music_buttons()
        )
        
        # Send log
        await app.send_message(
            LOGGER_ID,
            f"▶️ Playing in <code>{chat_id}</code>\n🎧 {title}\n👤 {requester}"
        )
        
        # Wait for song to finish (rough estimate)
        await asyncio.sleep(300)  # 5 minutes default
        
        # Clean up
        if chat_id in current_playing:
            del current_playing[chat_id]
            is_playing[chat_id] = False
        
    except Exception as e:
        print(f"❌ Play Error in {chat_id}: {e}")
        queue_col.update_one({"_id": task_id}, {"$set": {"status": "error"}})
        if chat_id in current_playing:
            del current_playing[chat_id]
            is_playing[chat_id] = False

# CALLBACK HANDLER
@app.on_callback_query()
async def music_controls(_, query):
    data = query.data
    chat_id = query.message.chat.id
    
    if data == "music_stop":
        try:
            await call_py.leave_group_call(chat_id)
            await query.message.edit_text("⏹ <b>Music Stopped</b>")
            if chat_id in current_playing:
                del current_playing[chat_id]
                is_playing[chat_id] = False
        except Exception as e:
            print(f"Stop error: {e}")
            
    elif data == "music_skip":
        try:
            await query.message.edit_text("⏭ <b>Skipping to next track...</b>")
            # Find next pending song
            next_task = queue_col.find_one({"chat_id": chat_id, "status": "pending"})
            if next_task:
                queue_col.update_one({"_id": next_task["_id"]}, {"$set": {"status": "processing"}})
                await process_task(next_task)
        except Exception as e:
            print(f"Skip error: {e}")
            
    elif data == "music_pause":
        try:
            await call_py.pause_stream(chat_id)
            await query.message.edit_text("⏸️ <b>Music Paused</b>")
        except Exception as e:
            print(f"Pause error: {e}")
            
    elif data == "music_resume":
        try:
            await call_py.resume_stream(chat_id)
            await query.message.edit_text("▶️ <b>Music Resumed</b>")
        except Exception as e:
            print(f"Resume error: {e}")
            
    elif data == "music_close":
        await query.message.delete()

# MONITOR QUEUE
async def music_monitor():
    print("🎵 Music monitor started...")
    while True:
        try:
            # Find pending task
            task = queue_col.find_one_and_update(
                {"status": "pending"},
                {"$set": {"status": "processing"}}
            )
            
            if task:
                chat_id = int(task["chat_id"])
                
                # Check if already playing in this chat
                if is_playing.get(chat_id):
                    print(f"⏳ Chat {chat_id} already has music playing, waiting...")
                    await asyncio.sleep(5)
                    continue
                    
                await process_task(task)
            else:
                await asyncio.sleep(3)
                
        except Exception as e:
            print(f"Monitor error: {e}")
            await asyncio.sleep(3)

# MANUAL PLAY COMMAND (For testing)
@app.on_message(filters.command("play") & filters.group)
async def manual_play(client, message):
    try:
        if len(message.command) < 2:
            await message.reply("Usage: /play song_name_or_url")
            return
            
        query = " ".join(message.command[1:])
        chat_id = message.chat.id
        
        # Add to queue
        queue_col.insert_one({
            "chat_id": chat_id,
            "link": f"https://t.me/{message.chat.username}" if message.chat.username else "",
            "song": query,
            "requester": message.from_user.mention if message.from_user else "Unknown",
            "status": "pending",
            "timestamp": asyncio.get_event_loop().time()
        })
        
        await message.reply(f"✅ Added to queue: {query}")
        
    except Exception as e:
        print(f"Manual play error: {e}")

# RUN
async def main():
    print("🚀 Starting Music Worker...")
    await app.start()
    print("✅ Pyrogram started")
    
    await call_py.start()
    print("✅ PyTgCalls started")
    
    await send_startup_log()
    
    # Start monitor
    asyncio.create_task(music_monitor())
    
    print("✅ Bot is ready! Waiting for tasks...")
    await idle()

if __name__ == "__main__":
    keep_alive()
    asyncio.run(main())
