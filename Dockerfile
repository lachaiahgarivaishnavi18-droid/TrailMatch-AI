FROM node:24-bookworm-slim AS frontend
WORKDIR /build
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.lock.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir "psycopg[binary]>=3.2,<4"
COPY backend/ ./backend/
COPY --from=frontend /build/dist ./frontend/dist/
RUN useradd --create-home research && mkdir /data && chown research:research /data
USER research
ENV DATABASE_URL=sqlite:////data/trialmatch.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
