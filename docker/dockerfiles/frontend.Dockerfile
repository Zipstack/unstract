# Multi-stage build for both development and production

# Global ARG available to all stages
ARG BUILD_CONTEXT_PATH=frontend

# Base stage with common setup
FROM node:20-alpine AS base
ARG BUILD_CONTEXT_PATH
WORKDIR /app

### FOR DEVELOPMENT ###
# Development stage for hot-reloading
FROM base AS development

# Copy only package files for dependency caching
COPY ${BUILD_CONTEXT_PATH}/package.json ${BUILD_CONTEXT_PATH}/package-lock.json ./
RUN npm install --ignore-scripts

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
CMD ["/bin/sh", "-c", "/app/generate-runtime-config.sh && npm start"]

### FOR PRODUCTION ###
# Builder stage for production build
FROM base AS builder
ARG REACT_APP_ENABLE_POSTHOG=true
ENV REACT_APP_BACKEND_URL=""
ENV REACT_APP_ENABLE_POSTHOG=${REACT_APP_ENABLE_POSTHOG}

# Copy package files and install dependencies
COPY ${BUILD_CONTEXT_PATH}/package.json ${BUILD_CONTEXT_PATH}/package-lock.json ./
RUN npm install --ignore-scripts

# Copy the rest of the application files
COPY ${BUILD_CONTEXT_PATH}/ .

# Build the React app
RUN npm run build

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

# Copy the environment script
COPY ${BUILD_CONTEXT_PATH}/generate-runtime-config.sh /docker-entrypoint.d/40-env.sh
RUN chmod +x /docker-entrypoint.d/40-env.sh

EXPOSE 80

USER nginx

# Start NGINX
CMD ["nginx", "-g", "daemon off;"]
