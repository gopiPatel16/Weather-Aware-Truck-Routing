# One container serves the API and the built React app (see docs/PLAN.md section 12).
FROM node:24-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install -r requirements.txt
COPY backend/ ./
COPY --from=frontend /app/frontend/dist ./frontend_dist
RUN DJANGO_ALLOW_INSECURE_KEY=1 python manage.py collectstatic --noinput
ENV PORT=8000
# One worker with threads: the in-process cache is shared and outbound calls run concurrently.
CMD ["sh", "-c", "gunicorn config.wsgi --bind 0.0.0.0:${PORT} --workers 1 --threads 8 --timeout 120"]
