FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
# Dépendances runtime : transformers, pandas, openpyxl, sentencepiece (DeBERTa), scikit-learn (train).
# PyTorch CUDA (Tesla T4) : wheels cu121 depuis l’index officiel PyTorch.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu121 \
      torch==2.2.2 && \
    pip install --no-cache-dir -r /app/requirements.txt && \
    python -c "import torch; assert torch.version.cuda is not None and torch.backends.cuda.is_built(), f'Invalid torch build: version={torch.__version__}, cuda={torch.version.cuda}, built={torch.backends.cuda.is_built()}'"

COPY main.py /app/main.py
COPY src /app/src
COPY scripts /app/scripts
COPY agent_recette_microservice /app/agent_recette_microservice

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
