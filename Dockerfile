FROM python:3.10-slim

WORKDIR /app

# 1. System Updates & Install Dependencies
# curl: Node download karne ke liye
# gnupg: Security keys ke liye
# ffmpeg & git: Music aur Python libs ke liye
RUN apt-get update && \
    apt-get install -y ffmpeg git curl gnupg && \
    apt-get clean

# 2. Install Node.js (Version 18) - ⚠️ ISKE BINA ERROR AAYEGA
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - && \
    apt-get install -y nodejs

# 3. Files Copy
COPY . .

# 4. Python Requirements Install
RUN pip install --no-cache-dir -r requirements.txt

# 5. Run Bot
CMD ["python", "main.py"]

