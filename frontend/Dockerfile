# Stage 1: Build React app
FROM node:20-alpine AS builder

WORKDIR /packages/shared-types
COPY packages/shared-types/package*.json ./
RUN npm install
COPY packages/shared-types/ ./

WORKDIR /app
COPY frontend/package*.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# Stage 2: Serve built React app with Nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
