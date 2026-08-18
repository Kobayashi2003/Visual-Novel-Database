# Architecture

## 1. Isolation

- Do not import from another application.
- Do not call another application over HTTP.
- Do not create a shared package — a common library would turn every change into
  a six-application change. When you change a file that is copied into each
  application, change every copy.
- Give each application its own database. Do not write to another application's
  database. When you read a table another application owns, do not create or
  migrate it — its schema belongs to the owner's migrations.
- Give each concern its own Redis logical database, recorded in `.env`. Do not
  share a keyspace.

## 2. The edge

- Give every externally reachable application the next free port, record it in
  `.env`, and add a matching `handle_path` block to `Caddyfile.snippet`. Leave an
  application without such a block localhost-only.
- Gate a route with `forward_auth` in `Caddyfile.snippet`. Do not check tokens
  inside an application.

## 3. The launcher

- Declare every child process as a `ProcSpec` with its `depends_on`, and start it
  through `procserve.Supervisor`. Do not spawn a process anywhere else.
