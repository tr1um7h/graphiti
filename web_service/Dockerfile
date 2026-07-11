# Graphiti Web Service - Next.js Application
# Multi-stage build: 基础镜像预装依赖，此处仅复制源码+构建
#
# 前置条件: 需先构建基础镜像
#   # arm64（本地开发）
#   docker build -f Dockerfile.base -t graphiti-web-base:node20 .
#   # amd64（生产环境）
#   docker buildx build --platform linux/amd64 -f Dockerfile.base -t graphiti-web-base:node20-amd64 --load .
#
# 构建业务镜像:
#   # arm64（本地开发）
#   docker build -t graphiti-web-service:latest .
#   # amd64（生产环境）
#   docker buildx build --platform linux/amd64 \
#     --build-arg BASE_IMAGE=graphiti-web-base:node20-amd64 \
#     -t graphiti-web-service:amd64 --load .

ARG BASE_IMAGE=graphiti-web-base:node20

# Stage 1: Build（基于预装依赖的基础镜像）
FROM ${BASE_IMAGE} AS builder

WORKDIR /app

# 复制源码并构建（node_modules 已在基础镜像中）
COPY . .
RUN npm run build

# Stage 2: Production Runner
FROM node:20-alpine AS runner

WORKDIR /app

# Set production environment
ENV NODE_ENV=production

# Copy package files and install production dependencies only
COPY --from=builder /app/package.json /app/package-lock.json* ./
RUN npm install --only=production --no-audit --no-fund

# Copy built application from builder stage
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.ts ./

# Expose port
EXPOSE 3000

# Start the application
CMD ["npm", "start"]
