FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app/box
COPY box/ ./
RUN pip install --no-cache-dir -r requirements.txt
ENV HOME=/data DATA_DIR=/data
CMD ["python", "start.py"]
