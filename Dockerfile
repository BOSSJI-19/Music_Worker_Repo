FROM python:3.10-slim

WORKDIR /app

# Git aur FFmpeg install karna zaroori hai
RUN apt-get update && \
    apt-get install -y ffmpeg git && \
    apt-get clean

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
