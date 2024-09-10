FROM node:16 AS builder

# Build-time environment variables 
ENV BUILD_CONTEXT_PATH frontend
ENV REACT_APP_BACKEND_URL ""

ARG REACT_APP_STRIPE_PUBLISHABLE_KEY
ENV REACT_APP_STRIPE_PUBLISHABLE_KEY $REACT_APP_STRIPE_PUBLISHABLE_KEY

# Set the working directory inside the container
WORKDIR /app

COPY ${BUILD_CONTEXT_PATH}/ .

RUN set -e; \
    # Install app dependencies
    npm install --ignore-scripts; \
    # Build the React app
    npm run build;


FROM nginx:1.25

LABEL maintainer="Zipstack Inc."

# Remove the default NGINX configuration
# RUN rm /etc/nginx/conf.d/default.conf

COPY --from=builder /app/build /usr/share/nginx/html
COPY --from=builder /app/nginx.conf /etc/nginx/nginx.conf

EXPOSE 80

USER nginx

# Start NGINX
CMD ["nginx", "-g", "daemon off;"]
