# --- Stage 1: Build the Frontend ---
FROM node:22-alpine AS builder

WORKDIR /app

# Copy only the files needed for installation to leverage Docker caching
COPY package.json pnpm-lock.yaml ./

RUN corepack enable && corepack install
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

# --- Stage 2: Production Server ---
FROM caddy:2-alpine

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=builder /app/dist /srv

EXPOSE 80 443
