# 1. Start from slim Python
FROM python:3.10-slim

# 2. Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      wkhtmltopdf ffmpeg build-essential && \
    rm -rf /var/lib/apt/lists/*

# 3. Create and set working dir
WORKDIR /app

# 4. Copy and install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your code
COPY . .

# 6. (Optional) Preload the Whisper model to speed up first request
RUN python - <<EOF
from faster_whisper import WhisperModel
WhisperModel("base")
EOF

# 7. Expose the port
EXPOSE 8000

# 8. Launch your app with Uvicorn
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
