FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Torch first so transitive deps resolve consistently.
# Use PyPI here to avoid corporate TLS trust failures against download.pytorch.org.
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install torch==2.5.1 torchaudio==2.5.1

COPY docker/diarization/requirements.txt /tmp/requirements.txt
RUN python -m pip install -r /tmp/requirements.txt

COPY docker/diarization/diarize.py /app/diarize.py

ENTRYPOINT ["python", "/app/diarize.py"]
