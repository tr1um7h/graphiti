FROM apache/age:dev_snapshot_PG16

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /var/run/postgresql \
    && chown postgres:postgres /var/run/postgresql

# Create init script to pre-install vector extension on first startup
COPY <<EOF /docker-entrypoint-initdb.d/10-create-vector-extension.sh
#!/bin/bash
# Use the same user as the initdb script (POSTGRES_USER or graphiti)
psql -U ${POSTGRES_USER:-graphiti} -d postgres -c "CREATE EXTENSION IF NOT EXISTS vector;" || true
psql -U ${POSTGRES_USER:-graphiti} -d template1 -c "CREATE EXTENSION IF NOT EXISTS vector;" || true
EOF
RUN chmod +x /docker-entrypoint-initdb.d/10-create-vector-extension.sh

USER postgres

# Point to the data directory so entrypoint doesn't re-init
ENV PGDATA=/var/lib/postgresql/16/main

USER root
