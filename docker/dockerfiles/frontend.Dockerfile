# Use a smaller base image for the builder stage
FROM node:16-alpine AS builder

# Build-time environment variables
ENV BUILD_CONTEXT_PATH=frontend
ENV REACT_APP_BACKEND_URL=""

# Set the working directory inside the container
WORKDIR /app

# Copy only the files needed for installing dependencies
COPY ${BUILD_CONTEXT_PATH}/package.json ${BUILD_CONTEXT_PATH}/package-lock.json ./

# Install dependencies (this layer will be cached unless package.json or package-lock.json changes)
RUN npm install --ignore-scripts

# Copy the rest of the application files
COPY ${BUILD_CONTEXT_PATH}/ .

# Build the React app
RUN npm run build

# Use a smaller base image for the final stage
FROM nginx:1.25-alpine

LABEL maintainer="Zipstack Inc."

# Remove the default NGINX configuration (if needed)
# RUN rm /etc/nginx/conf.d/default.conf

# Copy built assets from the builder stage
COPY --from=builder /app/build /usr/share/nginx/html

# Copy the server block configuration for nginx
COPY frontend/default.conf /etc/nginx/conf.d/default.conf

# Copy the environment script
COPY frontend/generate-runtime-config.sh /docker-entrypoint.d/40-env.sh
RUN chmod +x /docker-entrypoint.d/40-env.sh

EXPOSE 80

USER nginx

# Start NGINX
CMD ["nginx", "-g", "daemon off;"]
