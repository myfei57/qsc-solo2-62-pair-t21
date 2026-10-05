FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY pyproject.toml /app/pyproject.toml
COPY coldstore /app/coldstore

RUN python -m compileall -q /app/coldstore

EXPOSE 8080

CMD ["python", "-m", "coldstore", "--store", "/data/state.json", "--addr", "0.0.0.0:8080"]
