FROM bluenviron/mediamtx:1.21.1 AS mediamtx

FROM node:24-bookworm-slim AS frontend
WORKDIR /ui/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=mediamtx /mediamtx ./mediamtx
COPY app.py mediamtx.yml ./
COPY pc ./pc
COPY --from=frontend /ui/pc/operator_test.html ./pc/operator_test.html

EXPOSE 8000/tcp 8554/tcp 8889/tcp 8189/udp 8002/udp 8003/udp
CMD ["python", "-u", "app.py", "--bind-host", "0.0.0.0"]
