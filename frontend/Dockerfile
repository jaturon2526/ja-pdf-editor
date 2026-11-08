# ---------- stage 1: build ----------
FROM docker.io/library/node:22.12.0-bookworm-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# ---------- stage 2: serve ----------
# เปลี่ยนจาก alpine เป็น debian (bookworm) เพื่อแก้ปัญหา exec format error บน Apple Silicon
FROM docker.io/nginxinc/nginx-unprivileged:1.27-bookworm
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 8080

# Debian-based Nginx มักจะมี curl ติดมาให้แล้ว
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
