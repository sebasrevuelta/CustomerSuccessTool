#!/usr/bin/env bash
set -euo pipefail

POSTGRES_DB="${POSTGRES_DB:-customer_success}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"

DB_SECRET_EXPORTS="$(
python - <<'PY'
import shlex
from aws_secrets import get_internal_database_credentials

username, password = get_internal_database_credentials()
print(f"INTERNAL_DATABASE_USERNAME={shlex.quote(username)}")
print(f"INTERNAL_DATABASE_PASSWORD={shlex.quote(password)}")
PY
)"
eval "${DB_SECRET_EXPORTS}"

INTERNAL_DATABASE_HOST="${INTERNAL_DATABASE_HOST:-127.0.0.1}"
INTERNAL_DATABASE_PORT="${INTERNAL_DATABASE_PORT:-${POSTGRES_PORT}}"
INTERNAL_DATABASE_NAME="${INTERNAL_DATABASE_NAME:-${POSTGRES_DB}}"
DATABASE_URL="postgresql+psycopg2://${INTERNAL_DATABASE_USERNAME}:${INTERNAL_DATABASE_PASSWORD}@${INTERNAL_DATABASE_HOST}:${INTERNAL_DATABASE_PORT}/${INTERNAL_DATABASE_NAME}"
LOAD_DEMO_DATA="${LOAD_DEMO_DATA:-True}"
READ_FROM_INTERNAL_DATABASE="${READ_FROM_INTERNAL_DATABASE:-True}"

export POSTGRES_DB POSTGRES_PORT DATABASE_URL LOAD_DEMO_DATA READ_FROM_INTERNAL_DATABASE
export INTERNAL_DATABASE_USERNAME INTERNAL_DATABASE_PASSWORD INTERNAL_DATABASE_HOST INTERNAL_DATABASE_PORT INTERNAL_DATABASE_NAME

PG_MAJOR_VERSION="$(ls /etc/postgresql | sort -V | tail -n 1)"

sudo pg_ctlcluster "${PG_MAJOR_VERSION}" main start

until sudo -u postgres pg_isready -h 127.0.0.1 -p "${POSTGRES_PORT}" >/dev/null 2>&1; do
  sleep 1
done

sudo -u postgres psql -v ON_ERROR_STOP=1 --dbname postgres <<SQL
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${INTERNAL_DATABASE_USERNAME}') THEN
        CREATE ROLE ${INTERNAL_DATABASE_USERNAME} WITH LOGIN PASSWORD '${INTERNAL_DATABASE_PASSWORD}';
    ELSE
        ALTER ROLE ${INTERNAL_DATABASE_USERNAME} WITH LOGIN PASSWORD '${INTERNAL_DATABASE_PASSWORD}';
    END IF;
END
\$\$;
SQL

sudo -u postgres psql -v ON_ERROR_STOP=1 --dbname postgres <<SQL
SELECT 'CREATE DATABASE ${POSTGRES_DB} OWNER ${INTERNAL_DATABASE_USERNAME}'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${POSTGRES_DB}')\gexec
SQL

sudo -u postgres psql -v ON_ERROR_STOP=1 --dbname "${POSTGRES_DB}" -f /app/sql/customer_success_schema.sql

# Ensure the application role can read/write the initialized schema and table.
sudo -u postgres psql -v ON_ERROR_STOP=1 --dbname "${POSTGRES_DB}" <<SQL
GRANT CONNECT ON DATABASE ${POSTGRES_DB} TO ${INTERNAL_DATABASE_USERNAME};
GRANT USAGE ON SCHEMA public TO ${INTERNAL_DATABASE_USERNAME};
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ${INTERNAL_DATABASE_USERNAME};
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO ${INTERNAL_DATABASE_USERNAME};
ALTER TABLE "Customer_Success" OWNER TO ${INTERNAL_DATABASE_USERNAME};
ALTER TABLE feature_request OWNER TO ${INTERNAL_DATABASE_USERNAME};
ALTER TABLE "Customer_success_health_score" OWNER TO ${INTERNAL_DATABASE_USERNAME};
SQL

# Load demo data or Google Sheet data on startup.
if [[ "${LOAD_DEMO_DATA,,}" == "true" ]]; then
  sudo -u postgres psql -v ON_ERROR_STOP=1 --dbname "${POSTGRES_DB}" -f /app/sql/customer_success_sample_data.sql
  echo "Loaded demo data into Customer_Success, feature_request, and Customer_success_health_score tables."
else
  if [[ "${READ_FROM_INTERNAL_DATABASE,,}" == "true" ]]; then
    if ! python -c "from nurture_customer_success import sync_customer_success; import os; print(sync_customer_success(os.environ['DATABASE_URL']))"; then
      echo "Warning: failed loading Customer_Success data from Google Sheet at startup"
    fi
    if ! python -c "from nurture_feature_request import sync_feature_request; import os; print(sync_feature_request(os.environ['DATABASE_URL']))"; then
      echo "Warning: failed loading feature_request data from Google Sheet at startup"
    fi
    if ! python -c "from dashboard_page import persist_customer_success_health_score_snapshot; import os; print(persist_customer_success_health_score_snapshot(database_url=os.environ['DATABASE_URL'], use_last_activity_factor=True, use_contributors_factor=True, use_health_ae_factor=True, use_feature_request_factor=True))"; then
      echo "Warning: failed loading Customer_success_health_score snapshot at startup"
    else
      echo "Startup load completed for Customer_Success, feature_request, and Customer_success_health_score."
    fi
  else
    echo "READ_FROM_INTERNAL_DATABASE=false -> app will read from METABASE_DATABASE_URL; skipping internal startup sync."
  fi
fi

GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}"
GUNICORN_THREADS="${GUNICORN_THREADS:-4}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-180}"
GUNICORN_GRACEFUL_TIMEOUT="${GUNICORN_GRACEFUL_TIMEOUT:-30}"
GUNICORN_KEEPALIVE="${GUNICORN_KEEPALIVE:-5}"

exec gunicorn \
  --bind 0.0.0.0:5000 \
  --workers "${GUNICORN_WORKERS}" \
  --worker-class gthread \
  --threads "${GUNICORN_THREADS}" \
  --timeout "${GUNICORN_TIMEOUT}" \
  --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT}" \
  --keep-alive "${GUNICORN_KEEPALIVE}" \
  app:app
