import yt_dlp
import os
import asyncio

async def download_song(song_name, chat_id):
    """
    YouTube se song download karta hai (Render/Cloud Compatible)
    """
    
    # 1. Downloads Folder Check
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    # 2. Cookies File Check
    cookie_file = "cookies.txt"
    has_cookies = os.path.exists(cookie_file)

    # 3. ROBUST DOWNLOAD SETTINGS 🛡️
    ydl_opts = {
        'format': 'bestaudio/best', # Agar audio fail ho to video se nikal lega
        'outtmpl': f'downloads/{chat_id}.%(ext)s',
        'quiet': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'source_address': '0.0.0.0', # 🔥 CRITICAL FOR RENDER (IPv4 Force)
        
        # Audio Conversion (MP3 ensure karne ke liye)
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    # 🔥 Turbo Mode Check
    if has_cookies:
        ydl_opts['cookiefile'] = cookie_file
        print(f"🍪 Cookies Found! Turbo Mode Active.")
    else:
        print("⚠️ No Cookies Found. Using Normal Mode.")

    try:
        # 4. Running in Executor (Taaki Bot Hang na ho)
        loop = asyncio.get_event_loop()
        
        def run_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Pehle Search karo
                print(f"📥 Searching: {song_name}")
                info = ydl.extract_info(f"ytsearch:{song_name}", download=False)['entries'][0]
                
                # Fir Download karo
                ydl.download([info['webpage_url']])
                return info

        # Async Execution
        info = await loop.run_in_executor(None, run_download)
        
        # File Path (Post-processing ke baad MP3 ban jata hai)
        path = f"downloads/{chat_id}.mp3"
        title = info.get('title', 'Unknown Track')
        
        return path, title
            
    except Exception as e:
        print(f"❌ Download Error: {e}")
        return None, None
        
