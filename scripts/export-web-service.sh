#!/bin/bash
# 构建并导出 Web 服务 amd64 镜像
# 用于内网部署

set -e

echo "Building graphiti-web-service:amd64 image..."
docker buildx build --platform linux/amd64 -t graphiti-web-service:amd64 ./web_service/

echo "Exporting image to docker-images/graphiti-web-service-amd64-v1.tar..."
mkdir -p docker-images
docker save graphiti-web-service:amd64 -o docker-images/graphiti-web-service-amd64-v1.tar

echo "Done! Image exported to docker-images/graphiti-web-service-amd64-v1.tar"
