"""ProcSpec: the declarative description of one child process.

Name, command, environment, and the names of the children it depends on. The
launchers build a list of these; Supervisor turns the dependency names into a
start order.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class ProcSpec:
    """Declarative description of one supervised child process.

    A spec is data — no side effects at construction time. The Supervisor
    reads the list, sorts by `depends_on`, and launches each as a
    subprocess.Popen with stdout/stderr merged into one pipe so the log
    pump thread can prefix every line uniformly.

    Fields:
      name         Unique identifier across the spec list. Doubles as the
                   default log prefix (uppercased).
      cmd          argv list for subprocess.Popen. Pre-resolve the binary
                   path (shutil.which) when the spec-maker also gates on
                   binary existence — avoids a second PATH lookup at spawn.
      depends_on   Names of other specs that must start before this one. If a
                   referenced name is absent from the spec list (e.g. its
                   spec-maker returned None because the binary was missing),
                   the dep is treated as already-satisfied so the rest still
                   runs. Ordering alone is a race — a spawned process is not a
                   ready one — so a dependency that dependents cannot retry
                   against should also carry a `ready_check`.
      ready_check  Optional predicate polled after spawn until it returns True,
                   before any dependent is started. This is what turns
                   depends_on from "spawned first" into "usable first". Omit it
                   for services whose clients retry on their own.
      ready_timeout Seconds to wait for `ready_check` before giving up and
                   raising — a dependency that never comes up is fatal, and
                   failing here beats every dependent dying on first connect.
      cwd, env     Forwarded to subprocess.Popen as-is. Leave env=None to
                   inherit os.environ.
      log_prefix   Override for the log prefix (default: f"[{NAME}]").
      stop_cmd     Optional external command to request a graceful stop
                   (e.g. `pg_ctl stop -D <PGDATA> -m fast -w` for postgres).
                   Supervisor runs it synchronously, then waits up to
                   `stop_timeout` for the child to exit on its own. If the
                   child is still alive after that, Supervisor escalates to
                   terminate() and finally kill(). When None, Supervisor
                   skips straight to terminate() — fine for processes that
                   tolerate an abrupt TerminateProcess on Windows.
      stop_timeout Seconds to wait for the child to exit after the
                   graceful-stop request (or after terminate(), when
                   stop_cmd is None). Bumped above the default for
                   postgres because a "fast" shutdown still flushes WAL.
    """

    name: str
    cmd: List[str]
    depends_on: List[str] = field(default_factory=list)
    cwd: Optional[str] = None
    env: Optional[Dict[str, str]] = None
    log_prefix: Optional[str] = None
    ready_check: Optional[Callable[[], bool]] = None
    ready_timeout: float = 30.0
    stop_cmd: Optional[List[str]] = None
    stop_timeout: float = 5.0

    @property
    def prefix(self) -> str:
        return self.log_prefix or f"[{self.name.upper()}]"
