"""Process lifecycle for the launcher's children.

Owns the whole run: a topological start so dependencies come up first, one log
pump per child with the output prefixed and colourised by name, and a
reverse-topological shutdown when a signal arrives.

Deliberately not included: health probes and auto-restart. A child that dies is
reported, not resurrected — this supervises a development stack, where a crash
should be visible rather than papered over.
"""

import logging
import os
import signal
import subprocess
import sys
import threading
import time
import zlib
from typing import Dict, List, Optional

from .spec import ProcSpec


# ---------- console color ----------------------------------------------------
# Only the interactive console output is colored; the file logger keeps plain
# prefixes (no escape codes leak into logs/*.log). Errors/shutdown notices are
# red so they stand out; each service gets a stable color for its prefix so a
# glance tells you which child a line came from.

_RESET = "\033[0m"
_BOLD = "\033[1m"
_RED = "\033[91m"
# Red is reserved for errors, so it's absent from the per-service palette.
_PALETTE = [
    "\033[36m",   # cyan
    "\033[32m",   # green
    "\033[33m",   # yellow
    "\033[35m",   # magenta
    "\033[34m",   # blue
    "\033[96m",   # bright cyan
    "\033[92m",   # bright green
    "\033[95m",   # bright magenta
]


def _enable_windows_ansi() -> bool:
    """Turn on ENABLE_VIRTUAL_TERMINAL_PROCESSING so ANSI codes render in the
    Windows console. No-op success on terminals that already support it."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


def _supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        return _enable_windows_ansi()
    return True


class Supervisor:
    """Owns the lifecycle of a list of ProcSpecs.

    Usage:
        Supervisor(specs, logger=...).run()

    `run()` topologically starts every spec, installs a Ctrl+C handler that
    tears them down in reverse-topological order, and blocks until either
    a signal fires or KeyboardInterrupt escapes the sleep loop.

    The class is intentionally small. Auto-restart, health probes, and a
    status CLI are deliberate non-goals for this scope — see the module
    docstring for the growth path."""

    def __init__(self, specs: List[ProcSpec], logger: Optional[logging.Logger] = None):
        self.specs = specs
        self.logger = logger or logging.getLogger(__name__)
        self.processes: Dict[str, subprocess.Popen] = {}
        self._lock = threading.Lock()
        self._stopping = False
        self._color = _supports_color()
        # Stable per-service color (crc32, not the hash-randomized built-in
        # hash(), so a given service keeps the same color across runs).
        self._colors = {
            s.name: _PALETTE[zlib.crc32(s.name.encode()) % len(_PALETTE)]
            for s in specs
        }

    # ---------- console formatting -----------------------------------------

    def _prefix(self, spec: ProcSpec) -> str:
        """Colored prefix for console output (plain when color is off)."""
        if not self._color:
            return spec.prefix
        return f"{self._colors.get(spec.name, '')}{spec.prefix}{_RESET}"

    def _err(self, text: str) -> str:
        return f"{_RED}{text}{_RESET}" if self._color else text

    # ---------- ordering ----------------------------------------------------

    def _topological_order(self) -> List[ProcSpec]:
        """Kahn's algorithm over ProcSpec.depends_on.

        Edges that point at names not in the spec list are dropped (treated
        as already-satisfied). This is what lets the spec-maker pattern
        work: postgres isn't in the spec list at all (it runs as an external
        Windows service — see backend/scripts/pg-service.ps1), yet the flask/celery
        specs still declare `depends_on=["postgres"]`; the missing edge is
        treated as out-of-scope rather than missing, so they still start."""
        by_name = {s.name: s for s in self.specs}
        present = set(by_name)
        in_degree = {
            s.name: sum(1 for d in s.depends_on if d in present)
            for s in self.specs
        }
        ready = [name for name, n in in_degree.items() if n == 0]
        ordered: List[ProcSpec] = []
        seen = set()
        while ready:
            name = ready.pop(0)
            if name in seen:
                continue
            seen.add(name)
            ordered.append(by_name[name])
            for s in self.specs:
                if s.name in seen:
                    continue
                if name in s.depends_on:
                    in_degree[s.name] -= 1
                    if in_degree[s.name] == 0:
                        ready.append(s.name)
        if len(ordered) < len(self.specs):
            missing = [s.name for s in self.specs if s.name not in seen]
            raise ValueError(f"ProcSpec cycle or unresolved deps: {missing}")
        return ordered

    # ---------- launch / shutdown ------------------------------------------

    def _pump_logs(self, spec: ProcSpec, proc: subprocess.Popen) -> None:
        """Forward the child's output, and outlive anything one line can do.

        This thread is the pipe's only reader. If it stops, the pipe fills and
        the child blocks on its next write — a service that hangs with nothing
        reported anywhere, which is far worse than a lost log line. So no line
        is allowed to end the loop: the stream is decoded permissively (see
        `_start_one`) and a console that cannot render a character loses the
        character rather than the pump.

        The loop ends where it should: when the child closes its stdout.
        """
        assert proc.stdout is not None
        try:
            # proc.stdout is text-mode with stderr merged in. Iterating yields
            # lines as the child flushes them.
            for line in proc.stdout:
                self._emit(spec, line.rstrip("\n"))
        except Exception as e:
            # Reaching here means the pipe is about to go unread, which is the
            # one thing this thread exists to prevent. Say so.
            self.logger.error(f"{spec.prefix} log pump stopped: {e!r}")
            print(self._err(f"{spec.prefix} log pump stopped: {e!r}"), file=sys.stderr)
        finally:
            try:
                proc.stdout.close()
            except Exception:
                pass

    def _emit(self, spec: ProcSpec, line: str) -> None:
        """One line to the log file and to the console, neither able to raise."""
        try:
            self.logger.info(f"{spec.prefix} {line}")
        except Exception:
            pass
        try:
            print(f"{self._prefix(spec)} {line}")
        except Exception:
            pass

    def _start_one(self, spec: ProcSpec) -> None:
        marker = f"{_BOLD}starting{_RESET}" if self._color else "starting"
        print(f"{self._prefix(spec)} {marker}")
        self.logger.info(f"{spec.prefix} starting: {' '.join(spec.cmd)}")
        try:
            proc = subprocess.Popen(
                spec.cmd,
                cwd=spec.cwd,
                env=spec.env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                # Spelled out rather than left to the locale. Node and Caddy
                # write UTF-8 whatever the console's code page is, and a
                # locale-decoded pipe raises on their first byte that page
                # cannot express — which used to take the pump thread with it,
                # and the child's next write with that. `replace` extends the
                # same protection to a child that writes something else again.
                encoding="utf-8",
                errors="replace",
            )
        except (FileNotFoundError, OSError) as e:
            # FileNotFoundError is the common case (binary vanished between
            # the spec-maker's PATH check and now). OSError covers permission
            # / arg-list-too-long / etc. Don't crash the whole supervisor
            # on one bad child — log it and continue with the rest.
            self.logger.error(f"{spec.prefix} failed to spawn: {e}")
            print(self._err(f"\n!!! {spec.prefix} failed to spawn: {e}\n"), file=sys.stderr)
            return

        with self._lock:
            self.processes[spec.name] = proc
        threading.Thread(
            target=self._pump_logs, args=(spec, proc), daemon=True
        ).start()

        if spec.ready_check:
            self._await_ready(spec, proc)

    def _await_ready(self, spec: ProcSpec, proc: subprocess.Popen) -> None:
        """Block until the child is actually usable, not merely spawned.

        Topological order alone only guarantees Popen() was called first, which
        is a race: dependents can connect before the dependency is listening.
        Poll until it is, and treat never-ready as fatal — every dependent would
        otherwise die on its first connect, with a much less obvious error.
        """
        deadline = time.monotonic() + spec.ready_timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"{spec.name} exited with {proc.returncode} before becoming ready"
                )
            if spec.ready_check():
                self.logger.info(f"{spec.prefix} ready")
                return
            time.sleep(0.2)

        raise RuntimeError(
            f"{spec.name} was not ready within {spec.ready_timeout:g}s"
        )

    def start_all(self) -> None:
        for spec in self._topological_order():
            self._start_one(spec)

    def _stop_one(self, spec: ProcSpec, proc: subprocess.Popen) -> None:
        timeout = max(0.5, float(spec.stop_timeout))

        # 1) Graceful shutdown via spec-provided command (e.g. pg_ctl stop).
        if spec.stop_cmd:
            cmd_str = " ".join(spec.stop_cmd)
            self.logger.info(f"{spec.prefix} graceful stop: {cmd_str}")
            print(f"{self._prefix(spec)} graceful stop ({timeout:g}s timeout)")
            try:
                # The stop command itself is bounded by the same timeout so
                # a hung pg_ctl can't wedge the whole shutdown loop.
                subprocess.run(
                    spec.stop_cmd,
                    cwd=spec.cwd,
                    env=spec.env,
                    timeout=timeout,
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                )
            except subprocess.TimeoutExpired:
                self.logger.warning(f"{spec.prefix} stop_cmd timed out after {timeout:g}s")
                print(self._err(f"{spec.prefix} stop_cmd timed out"), file=sys.stderr)
            except Exception as e:
                self.logger.error(f"{spec.prefix} stop_cmd failed: {e}")
                print(self._err(f"{spec.prefix} stop_cmd failed: {e}"), file=sys.stderr)

            try:
                proc.wait(timeout=timeout)
                return
            except subprocess.TimeoutExpired:
                self.logger.warning(
                    f"{spec.prefix} did not exit within {timeout:g}s of graceful "
                    f"stop; escalating to terminate()"
                )
                print(
                    self._err(f"{spec.prefix} did not exit gracefully; terminating"),
                    file=sys.stderr,
                )

        # 2) terminate() — Popen default. On Windows this is TerminateProcess,
        #    which is abrupt; the stop_cmd path above exists for children that
        #    can't tolerate that. Redis/Caddy/Celery/Flask all handle
        #    terminate() cleanly enough.
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=timeout)
                return
            except subprocess.TimeoutExpired:
                self.logger.warning(
                    f"{spec.prefix} did not exit within {timeout:g}s of terminate; "
                    f"falling back to kill()"
                )
                print(self._err(f"{spec.prefix} kill (timeout)"), file=sys.stderr)
            except Exception as e:
                self.logger.error(f"{spec.prefix} terminate failed: {e}")
                print(self._err(f"{spec.prefix} terminate failed: {e}"), file=sys.stderr)

        # 3) Last resort.
        if proc.poll() is None:
            try:
                proc.kill()
                proc.wait(timeout=2)
            except Exception as e:
                self.logger.error(f"{spec.prefix} kill failed: {e}")
                print(self._err(f"{spec.prefix} kill failed: {e}"), file=sys.stderr)

    def stop_all(self) -> None:
        """Stop every running child in reverse-topological order.

        Reverse-topo means dependents (Flask) go down before their deps
        (Postgres) — avoids a tail of "connection refused" log spam from
        Flask while Postgres is already gone.

        Per-child shutdown is a three-step escalation:
          1. If `spec.stop_cmd` is set, run it and wait up to
             `spec.stop_timeout` for the child to exit on its own — the hook
             for any child that needs a real graceful stop rather than the
             abrupt terminate() below. No spec currently sets it (postgres,
             the original user, now runs as a Windows service).
          2. If the graceful path is unset or didn't finish in time, send
             terminate() (Ctrl-Break on Windows process groups, SIGTERM
             elsewhere) and wait again.
          3. Last resort: kill() (TerminateProcess / SIGKILL).
        """
        with self._lock:
            if self._stopping:
                return
            self._stopping = True

        order = list(reversed(self._topological_order()))
        for spec in order:
            proc = self.processes.get(spec.name)
            if proc is None or proc.poll() is not None:
                continue
            self._stop_one(spec, proc)

    # ---------- introspection ----------------------------------------------

    def status(self) -> Dict[str, str]:
        """Snapshot of {name: state}. Useful for future CLI / HTTP probes;
        not currently called from the launchers."""
        out: Dict[str, str] = {}
        for spec in self.specs:
            proc = self.processes.get(spec.name)
            if proc is None:
                out[spec.name] = "not-started"
            elif proc.poll() is None:
                out[spec.name] = "running"
            else:
                out[spec.name] = f"exited:{proc.returncode}"
        return out

    # ---------- main entrypoint --------------------------------------------

    def run(self) -> None:
        """Start everything, install signal handlers, block forever."""

        def handler(signum, frame):
            print(self._err("\nReceived interrupt; terminating processes..."))
            self.stop_all()
            sys.exit(0)

        # Windows has no SIGTERM and SIGINT only reaches us when the console
        # has focus; SIGBREAK (Ctrl+Break) covers the "another tool killed
        # the parent" case. Mirror the original launcher wiring.
        if sys.platform == "win32":
            signal.signal(signal.SIGBREAK, handler)
        signal.signal(signal.SIGINT, handler)
        if sys.platform != "win32":
            signal.signal(signal.SIGTERM, handler)

        try:
            self.start_all()
        except Exception as e:
            # A readiness gate failed part-way through. Whatever already started
            # is ours to clean up — otherwise the stack half-runs and orphans.
            print(self._err(f"\nStartup failed: {e}"))
            self.logger.error(f"startup failed: {e}")
            self.stop_all()
            sys.exit(1)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            handler(signal.SIGINT, None)
