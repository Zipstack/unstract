# Multi-stage build for both development and production

# Global ARG available to all stages
ARG BUILD_CONTEXT_PATH=frontend

# Base stage with common setup
FROM oven/bun:1-alpine AS base
ENV BUILD_CONTEXT_PATH=frontend
WORKDIR /app

### FOR DEVELOPMENT ###
# Development stage for hot-reloading
FROM base AS development
ARG BUILD_CONTEXT_PATH

# Copy only package files for dependency caching
COPY ${BUILD_CONTEXT_PATH}/package.json ${BUILD_CONTEXT_PATH}/bun.lock ./
RUN bun install --ignore-scripts

# Copy the rest of the application files
COPY ${BUILD_CONTEXT_PATH}/ /app/

# Copy the environment script
COPY ${BUILD_CONTEXT_PATH}/generate-runtime-config.sh /app/generate-runtime-config.sh
RUN chmod +x /app/generate-runtime-config.sh

# Set dev server to run on port 80 to match production nginx
ENV PORT=80
EXPOSE 80

# Run the environment config script before starting the
# dev server, as the node alpine base image does not
# auto-run /docker-entrypoint.d/*.
CMD ["/bin/sh", "-c", "/app/generate-runtime-config.sh && bun run start"]

### FOR PRODUCTION ###
# Builder stage for production build
FROM base AS builder
ENV VITE_BACKEND_URL=""

# Copy package files and install dependencies
COPY ${BUILD_CONTEXT_PATH}/package.json ${BUILD_CONTEXT_PATH}/bun.lock ./
RUN bun install --ignore-scripts

# Copy the rest of the application files
COPY ${BUILD_CONTEXT_PATH}/ .

# Build with Vite
RUN bun run build

# Production stage
FROM nginx:1.29.1-alpine AS production
ARG BUILD_CONTEXT_PATH
LABEL maintainer="Zipstack Inc."

# Copy built assets from the builder stage
COPY --from=builder /app/build /usr/share/nginx/html

# Copy custom NGINX configuration
COPY --from=builder /app/nginx.conf /etc/nginx/nginx.conf

# Create config directory and set permissions
RUN mkdir -p /usr/share/nginx/html/config && \
    chown nginx:nginx /usr/share/nginx/html/config && \
    chmod 755 /usr/share/nginx/html/config

# Inject runtime config script into index.html
RUN sed -i 's|</head>|    <script src="/config/runtime-config.js"></script>\n  </head>|' /usr/share/nginx/html/index.html

# Copy the environment script
COPY frontend/generate-runtime-config.sh /docker-entrypoint.d/40-env.sh
RUN chmod +x /docker-entrypoint.d/40-env.sh

EXPOSE 80

USER nginx

# Start NGINX
CMD ["nginx", "-g", "daemon off;"]
