# Stage 1: Build the React frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install
COPY . .
RUN npm run build

# Stage 2: Serve with FastAPI
FROM python:3.11-slim
WORKDIR /app

# Install system dependencies (e.g. for curl_cffi)
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend files
COPY main.py .
COPY slugs.json .

# Copy built frontend assets from Stage 1
COPY --from=frontend-builder /app/dist ./dist

# Expose the API port
EXPOSE 8000

# Start Uvicorn safely
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
