import yt_dlp
import os

async def download_song(song_name, chat_id):
    """
    YouTube se song fast download karta hai using cookies.txt (agar hai toh).
    Returns: (file_path, title)
    """
    
    # 1. Downloads Folder Check
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    # 2. Cookies File Check
    # Hum check karenge ki root folder mein 'cookies.txt' hai ya nahi
    cookie_file = "cookies.txt"
    has_cookies = os.path.exists(cookie_file)

    # 3. FAST DOWNLOAD SETTINGS ⚡
    ydl_opts = {
        'format': 'bestaudio',
        'outtmpl': f'downloads/{chat_id}.%(ext)s',
        'quiet': True,
        'noplaylist': True,
        'nocheckcertificate': True, # SSL Errors avoid karta hai
        'geo_bypass': True,         # Country restriction hatata hai
        'concurrent_fragment_downloads': 5, # Ek saath 5 tukde download karega (Super Fast)
    }

    # 🔥 Agar cookies.txt maujood hai, toh usse use karo
    if has_cookies:
        ydl_opts['cookiefile'] = cookie_file
        print(f"🍪 Cookies found! Using {cookie_file} for Turbo Speed.")
    else:
        print("⚠️ Warning: cookies.txt nahi mili. Normal speed use hogi.")

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Search & Download
            print(f"📥 Searching: {song_name}")
            info = ydl.extract_info(f"ytsearch:{song_name}", download=True)['entries'][0]
            
            # File details
            path = f"downloads/{chat_id}.{info['ext']}"
            title = info['title']
            
            return path, title
            
    except Exception as e:
        print(f"❌ Download Error: {e}")
        return None, None
        
