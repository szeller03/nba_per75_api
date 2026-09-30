FROM python:3.12-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    NBA_PER75_ROOT=/app/NBA_Per75 \
    HOST=0.0.0.0 \
    PORT=10000

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY local_api/ ./local_api/
# Package the authoritative regular-season SDI v4 season index used by
# Player Profile 5-Year Peak selection when the compact Railway cache is absent.
COPY regular_sdi_v4_wowy_player_seasons.csv ./bundled_data/regular_sdi_v4_wowy_player_seasons.csv
# The Career SDI builder uses this canonical player-season profile layer
# to derive TRB_pct when the career aggregate does not materialize it.
# Railway's persistent volume does not supply repository files to the image,
# so package this exact canonical source in the container.
COPY player_profiles_v1/ ./player_profiles_v1/
# Package the locked SDI specification with the application. The Railway
# persistent volume can contain an older copy, so the Career SDI builder must
# have access to the repository-controlled specification shipped with this build.
COPY player_subcategory_aggregation_v1/ ./player_subcategory_aggregation_v1/
# Package the authoritative headshot registry used by the runtime resolver.
COPY player_headshots_final_v1/ ./player_headshots_final_v1/
# The 584 uploaded/verified PNG headshots are committed at repository root.
# Copy them into the runtime directory so the uploaded PNGs are authoritative.
COPY *.png ./player_headshots_final_v1/
# Package the canonical master CSV archive.
COPY nba_per75_master_v46.csv.gz ./bundled_data/nba_per75_master_v46.csv.gz
COPY data/precomputed_5_year_peak/regular_profile_peaks_authoritative_v6.json ./bundled_data/regular_profile_peaks_authoritative_v6.json

EXPOSE 10000

CMD ["python", "local_api/nba_per75_local_api.py"]
