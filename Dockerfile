FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    NBA_PER75_ROOT=/app/NBA_Per75 \
    HOST=0.0.0.0 \
    PORT=10000

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY local_api/ ./local_api/

EXPOSE 10000

CMD ["python", "local_api/nba_per75_local_api.py"]
