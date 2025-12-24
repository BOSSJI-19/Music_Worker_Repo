from pyrogram import Client, filters

# .ping check karne ke liye
@Client.on_message(filters.command("ping", prefixes=".") & filters.me)
async def ping_check(client, message):
    await message.edit_text("⚡ **Pong!** (Legacy v0.9.7)")

# .stop manually rokne ke liye
@Client.on_message(filters.command(["stop", "end"], prefixes=".") & filters.me)
async def stop_music(client, message):
    chat_id = message.chat.id
    try:
        await client.leave_chat(chat_id)
        await message.edit_text("🛑 **Left Chat.**")
    except Exception as e:
        await message.edit_text(f"❌ Error: {e}")

# .join manually join karne ke liye
@Client.on_message(filters.command("join", prefixes=".") & filters.me)
async def join_chat(client, message):
    try:
        link = message.text.split()[1]
        await client.join_chat(link)
        await message.edit_text("✅ **Joined!**")
    except:
        await message.edit_text("❌ usage: `.join [link]`")
      
