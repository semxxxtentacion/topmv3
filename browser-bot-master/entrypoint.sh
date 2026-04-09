#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
if [ -n "$DATABASE_URL" ]; then
    echo "Waiting for PostgreSQL..."

    for i in $(seq 1 30); do
        if python -c "
from urllib.parse import urlparse
import socket, os, sys
url = os.environ.get('DATABASE_URL', '')
parsed = urlparse(url.replace('+asyncpg', ''))
host = parsed.hostname or 'localhost'
port = parsed.port or 5432
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.settimeout(2)
    s.connect((host, port))
    s.close()
    sys.exit(0)
except:
    sys.exit(1)
" 2>/dev/null; then
            echo "PostgreSQL is ready at $(python -c "from urllib.parse import urlparse; import os; p=urlparse(os.environ['DATABASE_URL'].replace('+asyncpg','')); print(f'{p.hostname}:{p.port or 5432}')")"
            break
        fi
        echo "Waiting for PostgreSQL ($i/30)..."
        sleep 2
    done
fi

case "$1" in
    server)
        echo "Starting API server..."
        exec python -m uvicorn generator.server:app --host 0.0.0.0 --port 8000
        ;;
    generate)
        echo "Running profile generation..."
        shift
        exec python -m generator "$@"
        ;;
    init-db)
        echo "Initializing database..."
        # Use sync URL for psql or python-based init
        python -c "
import asyncio, asyncpg, os

async def init():
    url = os.environ.get('DATABASE_URL', '').replace('postgresql+asyncpg://', 'postgresql://')
    conn = await asyncpg.connect(url)
    with open('schema.sql', 'r') as f:
        sql = f.read()
    await conn.execute(sql)
    await conn.close()
    print('Database initialized successfully')

asyncio.run(init())
"
        ;;
    *)
        exec "$@"
        ;;
esac
