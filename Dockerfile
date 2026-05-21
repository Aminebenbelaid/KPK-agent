FROM node:20-slim AS dashboard-build
WORKDIR /build
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm install
COPY dashboard/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY scrapers/ scrapers/
COPY scripts/ scripts/
COPY data/user_profile.yaml data/user_profile.yaml

COPY --from=dashboard-build /build/dist dashboard/dist

ENV HOST=0.0.0.0
ENV PORT=8000
ENV TRACKER_DB_PATH=data/tracker.db
ENV USER_PROFILE_PATH=data/user_profile.yaml

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
