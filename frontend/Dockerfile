# Stage 1: Build the static assets
FROM node:20-alpine AS builder

# 1. Install pnpm via corepack
RUN corepack enable && corepack prepare pnpm@latest --activate

WORKDIR /app

# 2. Copy only files needed for install to maximize Docker cache
COPY pnpm-lock.yaml package.json ./

# 3. Install dependencies
# --frozen-lockfile ensures the build fails if the lockfile needs updating
RUN pnpm install --frozen-lockfile

# 4. Copy source and build
COPY . .
RUN pnpm run build

# Stage 2: Export the files
FROM alpine
# Copy the built 'dist' folder to a standard location
COPY --from=builder /app/dist /dist
# Keep the container alive if needed, or just use as a volume source
CMD ["cp", "-rv", "/dist/.", "/shared_dist"]
