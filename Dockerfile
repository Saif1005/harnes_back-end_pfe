FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# This repository itself is the "harness_backend" package root.
COPY requirements.txt /srv/harness_backend/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r /srv/harness_backend/requirements.txt

COPY . /srv/harness_backend

EXPOSE 8030

CMD ["uvicorn", "harness_backend.main:app", "--host", "0.0.0.0", "--port", "8030"]

