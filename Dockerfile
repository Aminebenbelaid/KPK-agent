FROM node:20-slim AS dashboard-build
WORKDIR /build
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm install
COPY dashboard/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

# Tectonic: self-contained LaTeX engine for CV PDF generation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fL "https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz" -o /tmp/tectonic.tar.gz \
    && tar -xzf /tmp/tectonic.tar.gz -C /usr/local/bin tectonic \
    && rm /tmp/tectonic.tar.gz \
    && rm -rf /var/lib/apt/lists/*

# Persisted in the data volume so the package bundle is cached across restarts.
ENV TECTONIC_CACHE_DIR=/app/data/tectonic-cache

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY scrapers/ scrapers/
COPY cv_template/ cv_template/
COPY data/user_profile.yaml data/user_profile.yaml

COPY --from=dashboard-build /build/dist dashboard/dist

ENV HOST=0.0.0.0
ENV PORT=8000
ENV TRACKER_DB_PATH=data/tracker.db
ENV USER_PROFILE_PATH=data/user_profile.yaml

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
