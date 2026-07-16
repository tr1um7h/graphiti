FROM apache/age:dev_snapshot_PG16

USER root

# Install build dependencies and pg_jieba
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-16-pgvector \
        postgresql-server-dev-16 \
        # Build dependencies for pg_jieba
        build-essential \
        git \
        cmake \
        libglib2.0-dev \
        pkg-config \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/postgresql \
    && chown postgres:postgres /var/run/postgresql

# Build and install pg_jieba
WORKDIR /tmp
RUN git config --global http.sslVerify false \
    && git clone --depth 1 --recursive https://github.com/jaiminpan/pg_jieba.git \
    && cd pg_jieba \
    && mkdir build \
    && cd build \
    && cmake -DPostgreSQL_INCLUDE_DIR=/usr/include/postgresql/16 \
             -DPostgreSQL_LIBRARY=/usr/lib/postgresql/16/lib/postgres.lib .. \
    && make -j$(nproc) \
    && make install \
    && rm -rf /tmp/pg_jieba

WORKDIR /

# Create init script to pre-install extensions on first startup
COPY <<EOF /docker-entrypoint-initdb.d/10-create-extensions.sh
#!/bin/bash
# Use the same user as the initdb script (POSTGRES_USER or graphiti)
psql -U ${POSTGRES_USER:-graphiti} -d postgres -c "CREATE EXTENSION IF NOT EXISTS vector;" || true
psql -U ${POSTGRES_USER:-graphiti} -d template1 -c "CREATE EXTENSION IF NOT EXISTS vector;" || true
psql -U ${POSTGRES_USER:-graphiti} -d postgres -c "CREATE EXTENSION IF NOT EXISTS pg_jieba;" || true
psql -U ${POSTGRES_USER:-graphiti} -d template1 -c "CREATE EXTENSION IF NOT EXISTS pg_jieba;" || true
EOF
RUN chmod +x /docker-entrypoint-initdb.d/10-create-extensions.sh

USER postgres

# Point to the data directory so entrypoint doesn't re-init
ENV PGDATA=/var/lib/postgresql/16/main

USER root
