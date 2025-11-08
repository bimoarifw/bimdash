# --- Tahap 1: Build Frontend ---
FROM node:18-alpine AS builder
WORKDIR /app
COPY static/package.json static/package-lock.json ./
RUN npm install
COPY . .
RUN npm run build --prefix static && npm run build-css --prefix static

# --- Tahap 2: Aplikasi Final ---
FROM python:3.9-alpine
WORKDIR /app

# Install gunicorn
RUN apk add --no-cache gcc musl-dev linux-headers util-linux
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin kode aplikasi
COPY . .
# Salin aset frontend yang sudah jadi dari tahap builder
COPY --from=builder /app/static/dist /app/static/dist

EXPOSE 8535
CMD ["gunicorn", "--bind", "0.0.0.0:8535", "--workers", "3", "app:app"]