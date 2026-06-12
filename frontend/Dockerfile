# Multi-stage build for optimized production frontend
FROM node:22-alpine AS builder

WORKDIR /app

ARG VITE_API_URL=/api
ARG VITE_REPLY_API_URL=/api
ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_REPLY_API_URL=${VITE_REPLY_API_URL}

# Copy package files
COPY package*.json ./

# Install dependencies (dev deps required for Vite build)
RUN npm install

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy built app from builder (Vite outputs to /dist, NOT /build)
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1/ || exit 1

# Start nginx
CMD ["nginx", "-g", "daemon off;"]
