# Multi-stage build for both development and production

# Base stage with common setup
FROM oven/bun:1-alpine AS base
ENV BUILD_CONTEXT_PATH=frontend
WORKDIR /app

### FOR DEVELOPMENT ###
# Development stage for hot-reloading
FROM base AS development

# Copy only package files for dependency caching
COPY ${BUILD_CONTEXT_PATH}/package.json ${BUILD_CONTEXT_PATH}/bun.lock ./
RUN bun install --ignore-scripts

# Copy the rest of the application files
COPY ${BUILD_CONTEXT_PATH}/ /app/

EXPOSE 3000

CMD ["bun", "run", "start"]

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
