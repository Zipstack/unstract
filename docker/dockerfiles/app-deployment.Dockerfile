# Use an official Node.js runtime as the base image
FROM node:16 AS builder

ENV APP_TEMPLATE_PATH app-deployment
# Set the working directory inside the container
WORKDIR /app

# Copy package.json and package-lock.json to the container
COPY $APP_TEMPLATE_PATH/package*.json ./

# Copy the rest of the app's source code
COPY $APP_TEMPLATE_PATH/ .

# Install app dependencies
RUN npm install

# Build the React app
# Set environment variables
ENV REACT_APP_BACKEND_URL ""
RUN npm run build

# Use an official NGINX image as the base
FROM nginx:1.25 AS production-stage

# Copy the build files from the build-stage
COPY --from=builder /app/build /usr/share/nginx/html
COPY --from=builder /app/nginx.conf /etc/nginx/nginx.conf

# Expose port 80 for NGINX
EXPOSE 80
