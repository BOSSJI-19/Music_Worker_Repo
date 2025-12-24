import asyncio
import os
import sys
import logging
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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# FLASK SETUP
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "🎵 Music Worker is Alive & Running!"

@web_app.route('/health')
def health():
    return {"status": "healthy", "service": "music-bot"}

def run_web():
    port = int(os.environ.get("PORT", 8080))
    web_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

def keep_alive():
    web_thread = Thread(target=run_web, daemon=True)
    web_thread.start()
    logger.info("🌐 Flask server started")

# CLIENT SETUP
app = Client(
    "MusicWorker",
    api_id=API_ID,
    api_hash=API_HASH,
    session_string=SESSION,
    in_memory=True,
    workers=4
)

call_py = PyTgCalls(app)

# DATABASE
try:
    mongo = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    mongo.server_info()  # Test connection
    db = mongo["Music_Database"]
    queue_col = db["Music_Queue"]
    logger.info("✅ MongoDB connected successfully")
except Exception as e:
    logger.error(f"❌ MongoDB connection failed: {e}")
    sys.exit(1)

# GLOBAL STATE
active_chats = {}

# BUTTONS
def music_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⏹ Stop", callback_data="music_stop"),
            InlineKeyboardButton("⏭ Skip", callback_data="music_skip"),
            InlineKeyboardButton("⏸️ Pause", callback_data="music_pause")
        ],
        [
            InlineKeyboardButton("▶️ Resume", callback_data="music_resume"),
            InlineKeyboardButton("🔄 Restart", callback_data="music_restart")
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
        
        # Check cookies
        cookie_file = "cookies.txt"
        has_cookies = os.path.exists(cookie_file)
        
        # Check downloads folder
        if not os.path.exists("downloads"):
            os.makedirs("downloads")
        
        startup_msg = f"""
<b>🎹 Music Worker Online</b>

👤 {me.mention}
🆔 <code>{me.id}</code>
📛 @{me.username}

📊 <b>System Status:</b>
🍪 Cookies: {'✅ Active' if has_cookies else '❌ Missing'}
🗂️ Downloads: ✅ Ready
🗃️ Database: ✅ Connected
🎤 Voice: ✅ Ready
        """
        
        await app.send_message(LOGGER_ID, startup_msg)
        logger.info(f"✅ Bot started as @{me.username} (ID: {me.id})")
        
    except Exception as e:
        logger.error(f"Logger Error: {e}")

# CLEANUP FUNCTION
def cleanup_files(chat_id):
    """Delete downloaded files after playing"""
    try:
        file_path = f"downloads/{chat_id}.mp3"
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"🧹 Cleaned up file for chat {chat_id}")
    except Exception as e:
        logger.error(f"Cleanup error: {e}")

# MUSIC PLAYER FUNCTION
async def play_music(chat_id, file_path, title, requester):
    """Core function to play music in voice chat"""
    try:
        logger.info(f"🎵 Attempting to play in chat {chat_id}: {title}")
        
        # Join voice chat if not already joined
        try:
            await call_py.join_group_call(
                chat_id,
                InputStream(file_path, HighQualityAudio())
            )
            logger.info(f"✅ Joined voice chat {chat_id}")
        except Exception as join_error:
            logger.error(f"❌ Voice chat join failed: {join_error}")
            return False
        
        # Store active chat info
        active_chats[chat_id] = {
            "title": title,
            "file": file_path,
            "requester": requester,
            "status": "playing"
        }
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Play error in {chat_id}: {e}")
        return False

# TASK PROCESSOR
async def process_task(task):
    task_id = task["_id"]
    chat_id = int(task["chat_id"])
    query = task.get("song", "").strip()
    requester = task.get("requester", "Anonymous")
    link = task.get("link", "")
    
    logger.info(f"🔄 Processing task {task_id[:8]} for chat {chat_id}: {query[:50]}...")
    
    # Update status to processing
    queue_col.update_one({"_id": task_id}, {"$set": {"status": "processing"}})
    
    # Step 1: Check if bot is in group
    try:
        member = await app.get_chat_member(chat_id, "me")
        logger.info(f"✅ Bot is member of chat {chat_id}")
    except Exception:
        logger.warning(f"⚠️ Bot not in chat {chat_id}, attempting to join...")
        if link:
            try:
                await app.join_chat(link)
                await asyncio.sleep(2)
                logger.info(f"✅ Joined chat via link")
            except Exception as e:
                logger.error(f"❌ Failed to join chat: {e}")
                queue_col.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": "Can't join group"}})
                return
        else:
            queue_col.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": "Not in group"}})
            return
    
    # Step 2: Download song
    logger.info(f"📥 Downloading: {query}")
    file_path, title = await download_song(query, chat_id)
    
    if not file_path or not os.path.exists(file_path):
        logger.error(f"❌ Download failed for: {query}")
        queue_col.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": "Download failed"}})
        return
    
    logger.info(f"✅ Downloaded: {title} ({os.path.getsize(file_path)/1024/1024:.2f} MB)")
    
    # Step 3: Play music
    play_success = await play_music(chat_id, file_path, title, requester)
    
    if play_success:
        # Update task status
        queue_col.update_one({"_id": task_id}, {"$set": {"status": "playing", "title": title}})
        
        # Send playing notification
        try:
            msg = await app.send_message(
                chat_id,
                f"""
🎶 <b>Now Playing</b>

🎧 <b>Title:</b> {title}
👤 <b>Requested by:</b> {requester}
🕒 <b>Status:</b> Playing...

<i>Use buttons below to control playback</i>
                """,
                reply_markup=music_buttons()
            )
            
            # Store message ID for later control
            if chat_id in active_chats:
                active_chats[chat_id]["message_id"] = msg.id
        
        except Exception as e:
            logger.error(f"❌ Failed to send message: {e}")
        
        # Send log
        try:
            await app.send_message(
                LOGGER_ID,
                f"▶️ <b>Now Playing</b>\nChat: <code>{chat_id}</code>\nSong: {title}\nBy: {requester}"
            )
        except:
            pass
        
        # Wait for some time (simulate playing)
        try:
            await asyncio.sleep(180)  # 3 minutes
        except:
            pass
        
        # Cleanup
        cleanup_files(chat_id)
        
        # Remove from active
        if chat_id in active_chats:
            del active_chats[chat_id]
        
        # Mark as completed
        queue_col.update_one({"_id": task_id}, {"$set": {"status": "completed"}})
        
    else:
        queue_col.update_one({"_id": task_id}, {"$set": {"status": "failed", "error": "Playback failed"}})
        cleanup_files(chat_id)

# CALLBACK HANDLER
@app.on_callback_query()
async def handle_callback(_, query):
    data = query.data
    chat_id = query.message.chat.id
    
    try:
        if data == "music_stop":
            await call_py.leave_group_call(chat_id)
            await query.message.edit_text("⏹ <b>Music Stopped</b>")
            logger.info(f"⏹ Stopped music in {chat_id}")
            
        elif data == "music_skip":
            await query.message.edit_text("⏭ <b>Skipping to next song...</b>")
            # Find and process next task
            next_task = queue_col.find_one({"chat_id": chat_id, "status": "pending"})
            if next_task:
                await process_task(next_task)
            else:
                await query.message.edit_text("⏭ <b>No more songs in queue</b>")
                
        elif data == "music_pause":
            try:
                await call_py.pause_stream(chat_id)
                await query.message.edit_text("⏸️ <b>Music Paused</b>\n\nClick Resume to continue")
                logger.info(f"⏸️ Paused in {chat_id}")
            except Exception as e:
                await query.answer("❌ Unable to pause", show_alert=True)
                
        elif data == "music_resume":
            try:
                await call_py.resume_stream(chat_id)
                await query.message.edit_text("▶️ <b>Music Resumed</b>")
                logger.info(f"▶️ Resumed in {chat_id}")
            except Exception as e:
                await query.answer("❌ Unable to resume", show_alert=True)
                
        elif data == "music_restart":
            if chat_id in active_chats:
                file_path = active_chats[chat_id]["file"]
                title = active_chats[chat_id]["title"]
                requester = active_chats[chat_id]["requester"]
                
                await call_py.leave_group_call(chat_id)
                await asyncio.sleep(1)
                await play_music(chat_id, file_path, title, requester)
                await query.message.edit_text("🔄 <b>Music Restarted</b>")
                
        elif data == "music_close":
            await query.message.delete()
            
    except Exception as e:
        logger.error(f"Callback error: {e}")
        await query.answer("❌ Error occurred", show_alert=True)

# COMMAND HANDLERS
@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply("""
🎵 <b>Music Worker Bot</b>

I can play music in voice chats!

<b>Commands:</b>
/play [song name] - Play a song
/stop - Stop current song
/skip - Skip to next song
/queue - Show current queue
/ping - Check bot status

<b>Note:</b> Add me to group and give voice chat permission!
    """)

@app.on_message(filters.command("play") & filters.group)
async def play_command(client, message):
    if len(message.command) < 2:
        await message.reply("❌ Please provide a song name or URL\nUsage: /play song name")
        return
    
    query = " ".join(message.command[1:])
    chat_id = message.chat.id
    requester = message.from_user.mention if message.from_user else "Anonymous"
    
    # Add to queue
    queue_col.insert_one({
        "chat_id": chat_id,
        "link": f"https://t.me/{message.chat.username}" if message.chat.username else "",
        "song": query,
        "requester": requester,
        "status": "pending",
        "timestamp": asyncio.get_event_loop().time()
    })
    
    msg = await message.reply(f"✅ <b>Added to queue:</b>\n{query[:50]}...\n\n⏳ <i>Position in queue: Checking...</i>")
    
    # Count queue position
    queue_count = queue_col.count_documents({"chat_id": chat_id, "status": "pending"})
    await msg.edit_text(f"✅ <b>Added to queue:</b>\n{query[:50]}...\n\n📊 <i>Position in queue: #{queue_count}</i>")

@app.on_message(filters.command("stop") & filters.group)
async def stop_command(client, message):
    chat_id = message.chat.id
    try:
        await call_py.leave_group_call(chat_id)
        await message.reply("⏹ <b>Music Stopped</b>")
        logger.info(f"⏹ Stopped via command in {chat_id}")
    except Exception as e:
        await message.reply("❌ No music is playing")

@app.on_message(filters.command("skip") & filters.group)
async def skip_command(client, message):
    chat_id = message.chat.id
    msg = await message.reply("⏭ <b>Skipping to next song...</b>")
    
    # Find next pending task
    next_task = queue_col.find_one({"chat_id": chat_id, "status": "pending"})
    if next_task:
        await process_task(next_task)
    else:
        await msg.edit_text("⏭ <b>No more songs in queue</b>")

@app.on_message(filters.command("ping"))
async def ping_command(client, message):
    await message.reply(f"🏓 <b>Pong!</b>\n\nBot is alive and running!\nActive chats: {len(active_chats)}")

# QUEUE MONITOR
async def queue_monitor():
    """Monitor and process queued songs"""
    logger.info("🎵 Queue monitor started")
    
    while True:
        try:
            # Find a pending task
            task = queue_col.find_one_and_update(
                {"status": "pending"},
                {"$set": {"status": "processing"}},
                sort=[("timestamp", 1)]  # Process oldest first
            )
            
            if task:
                logger.info(f"🎯 Found task: {task.get('song', 'Unknown')[:30]}...")
                await process_task(task)
            else:
                # No tasks, sleep a bit
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"❌ Queue monitor error: {e}")
            await asyncio.sleep(5)

# MAIN FUNCTION
async def main():
    logger.info("=" * 50)
    logger.info("🚀 Starting Music Worker Bot")
    logger.info("=" * 50)
    
    try:
        # Start Pyrogram
        logger.info("Starting Pyrogram...")
        await app.start()
        
        # Test connection
        me = await app.get_me()
        logger.info(f"✅ Pyrogram started: @{me.username}")
        
        # Start PyTgCalls
        logger.info("Starting PyTgCalls...")
        await call_py.start()
        logger.info("✅ PyTgCalls started")
        
        # Send startup message
        await send_startup_log()
        
        # Start queue monitor
        asyncio.create_task(queue_monitor())
        
        logger.info("✅ Bot is fully operational!")
        logger.info("=" * 50)
        
        # Keep running
        await idle()
        
    except KeyboardInterrupt:
        logger.info("⏹ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
    finally:
        try:
            await app.stop()
            logger.info("✅ Bot stopped cleanly")
        except:
            pass

# ENTRY POINT
if __name__ == "__main__":
    # Start Flask server
    keep_alive()
    
    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        logger.error(f"🚨 Startup failed: {e}")
