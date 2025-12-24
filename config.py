import os

# Ye values Render ke Environment Variables se aayengi
API_ID = int(os.getenv("API_ID", "123456"))
API_HASH = os.getenv("API_HASH", "your_api_hash")
SESSION = os.getenv("SESSION", "your_string_session")

# Database (Wahi same URL jo Main Bot mein hai)
MONGO_URL = os.getenv("MONGO_URL", "mongodb+srv://...")

# Log Group ID (Jahan bot bataega ki wo zinda hai)
LOGGER_ID = int(os.getenv("LOGGER_ID", "-10012345678"))
