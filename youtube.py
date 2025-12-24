import yt_dlp
import os

async def download_song(song_name, chat_id):
    # Downloads folder check
    if not os.path.exists("downloads"):
        os.makedirs("downloads")

    ydl_opts = {
        'format': 'bestaudio',
        'outtmpl': f'downloads/{chat_id}.%(ext)s',
        'quiet': True,
        'noplaylist': True
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Search & Download
            info = ydl.extract_info(f"ytsearch:{song_name}", download=True)['entries'][0]
            
            path = f"downloads/{chat_id}.{info['ext']}"
            return path, info['title']
    except Exception as e:
        print(f"❌ Download Error: {e}")
        return None, None
      
