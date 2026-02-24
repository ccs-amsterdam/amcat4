# --- Stage 1: Build the Frontend ---
FROM node:20-alpine AS builder

WORKDIR /app

# Install pnpm (since you're using it in your monorepo)
RUN corepack enable && corepack prepare pnpm@latest --activate

# Copy only the files needed for installation to leverage Docker caching
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Copy the rest of the frontend source
COPY frontend/ .

# Build the Next.js app (assumes 'next build' generates an 'out' folder)
# Ensure your next.config.js has: output: 'export'
RUN pnpm build

# --- Stage 2: Production Server ---
FROM caddy:2-alpine

# Copy the Caddyfile from your production folder
COPY production/Caddyfile /etc/caddy/Caddyfile

# Copy the static build from the 'builder' stage to Caddy's default path
COPY --from=builder /app/dist /srv

EXPOSE 80 443
