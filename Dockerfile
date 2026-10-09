FROM python:3.12-slim

LABEL org.opencontainers.image.title="Block Buddy" \
      org.opencontainers.image.description="Kid-friendly Minecraft Bedrock builder" \
      org.opencontainers.image.source="https://github.com/TRU5T/block-buddy" \
      org.opencontainers.image.url="https://github.com/TRU5T/block-buddy"

WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/config', timeout=3)"
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
