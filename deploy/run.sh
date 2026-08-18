#!/usr/bin/env bash
# One-click launcher (Linux + Docker Engine).
#
#   ./deploy/run.sh
#
# Copies .env, ensures music/, builds the images, starts the stack, and waits
# for the edge. First run is slow (psycopg2 compiles, Next.js builds).
set -euo pipefail

DEPLOY="$(cd "$(dirname "$0")" && pwd)"
cd "$DEPLOY"

if [ ! -f .env ]; then
	cp .env.example .env
	echo ">> Created deploy/.env from template — set SECRET_KEY / JWT_SECRET_KEY before exposing it publicly."
fi
mkdir -p music

if ! docker info >/dev/null 2>&1; then
	echo "Docker engine not reachable. Is the daemon running (and your user in the 'docker' group)?" >&2
	exit 1
fi

echo ">> Building + starting..."
docker compose up -d --build

# Probe the app itself, not the origin root: the root is just a redirect served by
# Caddy, which would answer as soon as the edge is up and tell us nothing about
# whether the frontend behind it is ready.
url="http://localhost:30709/vndb"
printf ">> Waiting for %s " "$url"
ready=""
for _ in $(seq 1 90); do
	if curl -fsS "$url" >/dev/null 2>&1; then ready=1; break; fi
	sleep 3; printf "."
done
echo

if [ -z "$ready" ]; then
	echo ">> Gave up waiting. The stack is up but not serving — check: docker compose logs" >&2
	exit 1
fi

echo ">> Up. The site is at $url"
echo "   Logs:  docker compose logs -f        Stop:  docker compose down"
