# Graphiti Web Service - Next.js Application
# Multi-stage build for production deployment

# Stage 1: Build
FROM --platform=linux/amd64 node:20-alpine AS builder

WORKDIR /app

# Copy package files and install dependencies
COPY package.json package-lock.json* ./
RUN npm install --no-audit --no-fund

# Copy source code and build
COPY . .
RUN npm run build

# Stage 2: Production Runner
FROM --platform=linux/amd64 node:20-alpine AS runner

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
