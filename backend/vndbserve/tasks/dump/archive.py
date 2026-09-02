"""Read the tables out of VNDB's database dump.

The dump is a zstd-compressed tar of one file per table, each in PostgreSQL's
COPY text format, with the column names in a sibling `.header` file. It is read
as a stream: the archive holds a gigabyte of tables, most of it user lists and
image votes this service does not mirror, and streaming means only the wanted
tables are ever decoded.

Reading stops as soon as every wanted table has been seen, so a caller after a
few small tables does not pay for the ones that follow them in the archive.
"""

import io
import os
import tarfile
import threading
from datetime import datetime
from typing import Any, Iterator

import httpx
import zstandard

from vndbserve.errors import Failed, Unavailable

# How many past archives stay on disk. More than one so a republished archive
# can be compared against what it replaced; not many, at ~180 MB apiece.
KEEP_ARCHIVES = 3

# COPY's text format, as PostgreSQL writes it.
NULL = '\\N'
UNESCAPE = {'\\': '\\', 'b': '\b', 'f': '\f', 'n': '\n', 'r': '\r',
            't': '\t', 'v': '\v'}

# Read granularity for the streamed archive.
CHUNK = 1 << 20


def unescape(field: str) -> str | None:
    """One COPY field as its value, or None for the null marker."""
    if field == NULL:
        return None
    if '\\' not in field:
        return field
    out = []
    i = 0
    while i < len(field):
        char = field[i]
        if char != '\\' or i + 1 >= len(field):
            out.append(char)
            i += 1
            continue
        nxt = field[i + 1]
        out.append(UNESCAPE.get(nxt, nxt))
        i += 2
    return ''.join(out)


def read_lines(stream) -> Iterator[bytes]:
    """The file's lines, cut out of raw chunks.

    Not through a text wrapper: inside a streamed tar the member is not
    seekable, which a text wrapper insists on.
    """
    pending = b''
    while True:
        chunk = stream.read(CHUNK)
        if not chunk:
            break
        pending += chunk
        lines = pending.split(b'\n')
        pending = lines.pop()
        for line in lines:
            if line:
                yield line
    if pending:
        yield pending


def _row(line: bytes, columns: list[str]) -> dict[str, Any]:
    return dict(zip(columns, (unescape(f) for f in line.decode('utf-8').split('\t'))))


def cached_archive(directory: str, url: str, published: datetime,
                   keep: int = KEEP_ARCHIVES) -> str:
    """The archive for `published`, downloading it only if it is not here yet.

    Kept on disk because one download serves every resource type read out of
    it: fetching it per type would pull the same hundreds of megabytes over and
    over. Older copies are pruned rather than kept forever, and the newest few
    stay so that a republished archive can still be compared against what it
    replaced.
    """
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f'vndb-db-{published:%Y%m%d}.tar.zst')
    if os.path.exists(path):
        return path

    partial = f'{path}.{os.getpid()}.{threading.get_ident()}.part'
    try:
        with httpx.stream('GET', url, follow_redirects=True, timeout=3600) as response:
            response.raise_for_status()
            with open(partial, 'wb') as out:
                for chunk in response.iter_bytes():
                    out.write(chunk)
    except httpx.HTTPError as exc:
        _discard(partial)
        raise Unavailable('dump_unreachable',
                          "The VNDB database dump could not be fetched.",
                          {'url': url, 'cause': repr(exc)}) from exc
    except OSError as exc:
        _discard(partial)
        raise Failed('internal_error', "The dump could not be written to disk.",
                     {'path': partial, 'cause': repr(exc)}) from exc

    # Renamed only once whole, so an interrupted download is never mistaken for
    # a usable archive on the next run.
    os.replace(partial, path)
    _prune(directory, keep)
    return path


def _discard(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def _prune(directory: str, keep: int) -> None:
    archives = sorted(f for f in os.listdir(directory)
                      if f.startswith('vndb-db-') and f.endswith('.tar.zst'))
    for name in archives[:-keep] if keep else archives:
        _discard(os.path.join(directory, name))


def read_tables(source: str, wanted: set[str]) -> dict[str, list[dict[str, Any]]]:
    """The named tables, read from a dump held at `source` — a path or a URL.

    Headers arrive in the archive next to their data, so a table's columns are
    known by the time its rows are read.
    """
    # A table's data comes before its `.header` in the archive, so the rows are
    # held as raw lines and given their column names once both have arrived.
    lines: dict[str, list[bytes]] = {}
    headers: dict[str, list[str]] = {}
    pending = set(wanted)

    opened = _open(source)
    try:
        with zstandard.ZstdDecompressor().stream_reader(opened) as raw:
            with tarfile.open(fileobj=raw, mode='r|') as archive:
                for member in archive:
                    if not member.isfile() or not member.name.startswith('db/'):
                        continue
                    name = member.name[len('db/'):]
                    is_header = name.endswith('.header')
                    table = name[:-len('.header')] if is_header else name
                    if table not in wanted:
                        continue
                    handle = archive.extractfile(member)
                    if handle is None:
                        continue
                    if is_header:
                        headers[table] = handle.read().decode('utf-8').strip().split('\t')
                    else:
                        lines[table] = list(read_lines(handle))
                    if table in headers and table in lines:
                        pending.discard(table)
                        if not pending:
                            break
    finally:
        opened.close()

    tables = {table: [_row(line, headers[table]) for line in rows]
              for table, rows in lines.items() if table in headers}
    missing = wanted - set(tables)
    if missing:
        raise Unavailable('dump_incomplete',
                          "The dump is missing tables this service needs.",
                          {'missing': sorted(missing)})
    return tables


def _open(source: str):
    if source.startswith(('http://', 'https://')):
        try:
            response = httpx.stream('GET', source, follow_redirects=True, timeout=1800)
            entered = response.__enter__()
            entered.raise_for_status()
            return _ResponseReader(response, entered)
        except httpx.HTTPError as exc:
            raise Unavailable('dump_unreachable',
                              "The VNDB database dump could not be fetched.",
                              {'url': source, 'cause': repr(exc)}) from exc
    return open(source, 'rb')


class _ResponseReader(io.RawIOBase):
    """A streamed response as a file, so the archive is never held whole."""

    def __init__(self, manager, response):
        self._manager = manager
        self._chunks = response.iter_bytes()
        self._buffer = b''

    def readable(self) -> bool:
        return True

    def readinto(self, target) -> int:
        while not self._buffer:
            try:
                self._buffer = next(self._chunks)
            except StopIteration:
                return 0
        size = min(len(target), len(self._buffer))
        target[:size] = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return size

    def close(self) -> None:
        try:
            self._manager.__exit__(None, None, None)
        except Exception:
            pass
        super().close()
