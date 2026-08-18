#!/usr/bin/env bash
# Runs once, on the Postgres container's FIRST boot (empty data dir), via the
# official image's /docker-entrypoint-initdb.d hook. Creates the four
# per-service databases the backends expect (vndbserve / imgserve / userserve /
# transserve), all owned by the default POSTGRES_USER.
set -euo pipefail

for db in vndbserve imgserve userserve transserve; do
	echo "[postgres-init] Creating database '${db}' (if absent) ..."
	psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
		SELECT 'CREATE DATABASE ${db}'
		WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = '${db}')\gexec
	EOSQL
done
