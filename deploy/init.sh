#!/usr/bin/env bash
# One-shot init job: wait for Postgres, run migrations, seed the translation
# memory. Every long-running backend service depends on this completing
# successfully (service_completed_successfully) so they never race an
# un-migrated DB.
#
# - vndbserve / imgserve / userserve own Alembic migrations -> `flask db upgrade`.
# - transserve has no Alembic versions: create_app() does db.create_all() on
#   boot, so we just seed it from the bundled init.json (the only data this
#   whole deployment ships; everything else is crawled from scratch).
set -euo pipefail

echo "[init] Waiting for Postgres at ${POSTGRES_HOST:-postgres}:5432 ..."
until pg_isready -h "${POSTGRES_HOST:-postgres}" -U "${POSTGRES_USER:-postgres}" -q; do
	sleep 1
done
echo "[init] Postgres is ready."

# Use Flask's factory-argument form to pass enable_scheduler=False: a CLI run
# must not spin up the APScheduler crawl threads (they'd keep the process alive
# and hang the one-shot job).
for app in vndbserve imgserve userserve; do
	echo "[init] Migrating ${app} ..."
	flask --app "${app}:create_app(enable_scheduler=False)" db upgrade --directory "${app}/migrations"
done

echo "[init] Seeding transserve translation memory from data/init.json ..."
flask --app "transserve:create_app(enable_scheduler=False)" seed-init -f transserve/data/init.json --replace

echo "[init] Done. Backends may start; vndbserve/imgserve will crawl on their schedule."
