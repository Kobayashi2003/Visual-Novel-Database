"""Backend process launcher (dev + prod).

    python launch.py dev [--waitress]
    python launch.py prod

(usually invoked via `pixi run dev` / `pixi run prod` — see pixi.toml).

Builds a ProcSpec list and hands it to procserve.Supervisor, which does the
topological start, log aggregation and reverse-topological shutdown.

Stacks: Redis + vndbserve/imgserve Celery workers + the Flask servers. dev adds the
Flower dashboards and uses the Flask dev server; prod uses Waitress.

This launcher owns the BACKEND only. The Caddy edge is a whole-app concern — it
also fronts the Next.js frontend — so it belongs to ../start-prod.ps1, which owns
both halves. Keeping it here forced the frontend's port to be plumbed through the
backend just to configure the proxy.

Postgres is likewise not launched here: it runs as a Windows service (see
scripts/pg-service.ps1) so the SCM owns its shutdown. The flask/celery specs
still declare depends_on=["postgres"]; with no postgres spec in the list,
Supervisor's topo sort treats that edge as already-satisfied.
"""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import socket
import sys
from logging.handlers import RotatingFileHandler
from typing import List, Optional

from dotenv import load_dotenv

from procserve import ProcSpec, Supervisor


# Load backend/.env into the parent process *before* the spec-makers run —
# they read PG_DATA, DATA_FOLDER, the celery broker / flower ports,
# etc. from os.environ. The Flask children also load .env themselves (see
# vndbserve/config.py), but that's too late for the launcher's own decisions.
load_dotenv()

# Consolidate logs under the repo-root logs/ dir (launch.py lives in backend/,
# so its parent is the repo root) — matches each app's logger.py.
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)
os.environ["PYTHONUNBUFFERED"] = "1"
# Don't litter the source tree with __pycache__/*.pyc — set it here (not just
# in pixi.toml's [activation.env]) so it holds even when launch.py is run with
# a bare `python launch.py`, and so every child interpreter inherits it.
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

logger = logging.getLogger("launch")


def _setup_logging(mode: str) -> None:
    """Log INFO+ to logs/<mode>.log and ERROR+ to the console. The spec-makers
    below log through this same logger, so their missing-binary warnings land
    in the file too."""
    logger.setLevel(logging.INFO)
    file_handler = RotatingFileHandler(os.path.join(_LOG_DIR, f"launch-{mode}.log"), maxBytes=1024 * 1024 * 5)
    file_handler.setLevel(logging.INFO)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.ERROR)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


# ---------- shared binary-existence check ------------------------------------


def _check_binary(name: str, install_hint: str = "") -> Optional[str]:
    """Resolve `name` on PATH; on miss, log + print a prominent warning so
    the user notices before the subprocess silently fails to spawn."""
    path = shutil.which(name)
    if path is None:
        msg = f"`{name}` not found on PATH. {install_hint}".rstrip()
        logger.warning(f"[MISSING] {msg}")
        print(
            f"\n!!! [MISSING] {msg}\n"
            f"    Skipping the associated service; other services will still start.\n",
            file=sys.stderr,
        )
    return path


# ---------- external services -----------------------------------------------


def _redis_accepting(host: str = "127.0.0.1", port: int = 6379) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def make_redis_spec() -> Optional[ProcSpec]:
    redis_bin = _check_binary(
        "redis-server",
        "Install Redis (Memurai/Redis-Windows, or via WSL) and make sure "
        "`redis-server` is on PATH — or run Redis as a service/daemon and "
        "remove this spec from the launcher.",
    )
    if not redis_bin:
        return None

    return ProcSpec(
        name="redis",
        cmd=[
            redis_bin,
            "--save", '""',          # disable RDB snapshots
            "--appendonly", "no",    # disable AOF persistence
        ],
        # Celery and Flask connect to Redis as they boot. depends_on only orders
        # the spawns, so without this gate they race a Redis that may not be
        # listening yet — it just happens to win, because Redis starts in
        # milliseconds. Wait for the socket instead of relying on that.
        ready_check=_redis_accepting,
        log_prefix="[REDIS]",
    )


# ---------- celery / flower / flask (python -c bootstraps) ------------------

# Using sys.executable instead of a bare 'python' so the child runs under
# the *exact* same interpreter as the parent — matters when the parent is
# launched via `pixi run` (parent's python is the pixi env's python, and
# we want the child to use that too rather than whatever 'python' on PATH
# happens to be).
_PY = sys.executable


def make_celery_spec(app_name: str) -> ProcSpec:
    concurrency = int(os.environ.get("CELERY_CONCURRENCY", os.cpu_count() or 4))
    bootstrap = (
        f"from {app_name} import create_app;"
        f"app = create_app(enable_scheduler=False);"
        f"config = app.config;"
        f"celery = app.celery;"
        # quiet=True suppresses Celery's startup banner (the ASCII art +
        # config/queues/tasks dump). Worker.emit_banner() is guarded by
        # `not quiet`, so real task logs still come through at loglevel=info.
        f"celery.Worker(pool='threads', concurrency={concurrency}, "
        f"loglevel='info', quiet=True).start();"
    )
    return ProcSpec(
        name=f"{app_name}_celery",
        cmd=[_PY, "-c", bootstrap],
        depends_on=["redis", "postgres"],
        log_prefix=f"[{app_name.upper()} CELERY]",
    )


def make_flower_spec(app_name: str) -> ProcSpec:
    # Flower only needs the broker URL and its port. Those map straight from
    # env (see each app's config.py: CELERY_BROKER_URL / FLOWER_PORT are read
    # verbatim from {APP}_CELERY_BROKER_URL / {APP}_FLOWER_PORT), so read them
    # directly instead of paying a full create_app() just to look them up.
    upper = app_name.upper()
    broker = os.environ[f"{upper}_CELERY_BROKER_URL"]
    port = os.environ[f"{upper}_FLOWER_PORT"]
    return ProcSpec(
        name=f"{app_name}_flower",
        cmd=["celery", f"--broker={broker}", "flower", f"--port={port}"],
        depends_on=[f"{app_name}_celery"],
        log_prefix=f"[{app_name.upper()} FLOWER]",
    )


def make_flask_spec(app_name: str, *, use_waitress: bool) -> ProcSpec:
    if use_waitress:
        bootstrap = (
            f"from waitress import serve;"
            f"import {app_name};"
            f"app = {app_name}.create_app();"
            f"config = app.config;"
            f"serve(app, host=config['APP_HOST'], port=config['APP_PORT'],"
            f"      threads=config.get('WAITRESS_THREADS', 4));"
        )
        prefix = f"[{app_name.upper()} WAITRESS]"
    else:
        bootstrap = (
            f"from {app_name} import create_app;"
            f"app = create_app();"
            f"config = app.config;"
            f"app.run(host=config['APP_HOST'],"
            f"port=config['APP_PORT'],"
            f"debug=config['DEBUG'],"
            f"use_reloader=config['USE_RELOADER']);"
        )
        prefix = f"[{app_name.upper()} FLASK]"

    return ProcSpec(
        name=f"{app_name}_flask",
        cmd=[_PY, "-c", bootstrap],
        depends_on=["postgres", "redis"],
        log_prefix=prefix,
    )


# ---------- spec assembly ----------------------------------------------------


def build_specs(mode: str, *, use_waitress: bool) -> List[ProcSpec]:
    """Assemble the stack for `mode` ("dev" | "prod"). Nones (missing-binary
    skips) are filtered out at the end. The stacks differ only in Flower (dev
    only) and Waitress-vs-Flask-dev for the Flask apps.
    """
    specs: List[Optional[ProcSpec]] = [make_redis_spec()]
    for app in ("vndbserve", "imgserve"):
        specs.append(make_celery_spec(app))
        if mode == "dev":
            specs.append(make_flower_spec(app))
        specs.append(make_flask_spec(app, use_waitress=use_waitress))
    # logserve is a developer diagnostics tool over the vndbserve `logs` table. It has
    # no route in Caddyfile.snippet, so it stays loopback-only and is never
    # reachable through the public edge.
    for app in ("userserve", "transserve", "musicserve", "logserve"):
        specs.append(make_flask_spec(app, use_waitress=use_waitress))

    return [s for s in specs if s is not None]


def main():
    parser = argparse.ArgumentParser(description="VNDB backend process launcher")
    sub = parser.add_subparsers(dest="mode", required=True)

    p_dev = sub.add_parser("dev", help="Dev stack (Flask dev server + Flower)")
    p_dev.add_argument(
        "--waitress", action="store_true",
        help="Use Waitress WSGI server instead of the Flask dev server",
    )

    sub.add_parser("prod", help="Prod stack (Waitress)")

    args = parser.parse_args()
    _setup_logging(args.mode)

    if args.mode == "prod":
        specs = build_specs("prod", use_waitress=True)
    else:
        specs = build_specs("dev", use_waitress=args.waitress)

    Supervisor(specs, logger=logger).run()


if __name__ == "__main__":
    main()
