FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    NBA_PER75_ROOT=/app/NBA_Per75 \
    HOST=0.0.0.0 \
    PORT=10000

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY local_api/ ./local_api/
# The Career SDI builder uses this canonical player-season profile layer
# to derive TRB_pct when the career aggregate does not materialize it.
# Railway's persistent volume does not supply repository files to the image,
# so package this exact canonical source in the container.
COPY player_profiles_v1/ ./player_profiles_v1/

EXPOSE 10000

CMD ["python", "local_api/nba_per75_local_api.py"]
