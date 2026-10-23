# Study Trail Builder - Angular frontend image (Req 7.1, 7.6)
# Multi-stage: build the Angular app, then serve the static output with nginx.

# Stage 1: build the production bundle
FROM node:22-alpine AS build

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY package.json package-lock.json ./
RUN npm ci

# Copy the rest of the source and build (production config is the default)
COPY . .
RUN npx ng build

# Stage 2: serve the static build with nginx
FROM nginx:alpine

# Angular (@angular/build:application) emits the browser bundle under dist/frontend/browser
COPY --from=build /app/dist/frontend/browser /usr/share/nginx/html

# nginx config: SPA fallback + reverse proxy for /api to the backend service
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
