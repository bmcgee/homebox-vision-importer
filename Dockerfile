# Stage 1: Build Mobile-First Svelte Frontend
FROM node:20-slim AS frontend-builder
WORKDIR /app/frontend
ENV NODE_ENV=development
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Production Python FastAPI Backend
FROM python:3.12-slim
WORKDIR /app

# Install curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files and built frontend dist
COPY app.py .
COPY templates/ templates/
COPY --from=frontend-builder /app/frontend/dist /app/frontend/dist

# Create persistent data volume directory
RUN mkdir -p /data

EXPOSE 8000

# Run FastAPI app with Uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
