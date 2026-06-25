FROM node:22-alpine AS builder

WORKDIR /app

# Install deps (cache layer)
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

# Build args for Vite env vars
ARG VITE_API_BASE=/api/v1
ENV VITE_API_BASE=$VITE_API_BASE

# Copy source
COPY . .

# Build for production
RUN npm run build

# ---- Runtime stage ----
FROM nginx:1.27-alpine

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config: SPA fallback + API reverse proxy
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
