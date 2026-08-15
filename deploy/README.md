# Deploy — Docker stack

One-command, self-contained deployment of the whole site. Only the **translation
memory** is bundled (`backend/transserve/data/init.json`); everything else is
crawled from the VNDB Kana API on first run.

---

## 1. Environment & dependencies

A **Linux** Docker engine + Compose v2 (the images are Linux containers).

- **Linux host:** `sudo apt-get install -y docker.io docker-compose-v2` (then add
  your user to the `docker` group and re-login).
- **Windows:** the engine must be WSL2-backed — **Docker Desktop / Rancher
  Desktop**, or **Docker Engine inside a WSL2 distro**. scoop's bare `dockerd`
  only runs *Windows* containers and cannot run this stack.

The crawled image cache (the `appdata` volume) grows over time.

---

## 2. Services & ports

Only **Caddy** is published (`:30709`); it is the single origin and routes to
every backend by path prefix. Everything else is internal.

| Service | Role | Port |
| --- | --- | --- |
| `caddy` | public ingress | **30709** (published) |
| `frontend` | Next.js standalone | 5010 |
| `vndb` / `vndb-celery` | VN data API + crawl worker | 5000 |
| `imgserve` / `imgserve-celery` | image cache + fetch worker | 5001 |
| `userserve` | accounts / auth | 5002 |
| `transserve` | translation | 5003 |
| `musicserve` | soundtrack library + admin upload | 5004 |
| `postgres` / `redis` | data + cache/broker | 5432 / 6379 |
| `init` | one-shot: create DBs, migrate, seed translation memory, then exit | — |

---

## 3. Running

```bash
cd deploy
cp .env.example .env          # edit the secrets (SECRET_KEY, JWT_SECRET_KEY, ...)
docker compose up -d --build
```

Open <http://localhost:30709>. `init` runs first (DBs + migrations + seed), then
the services start. Data stays empty until `vndb`/`imgserve` crawl — set
`CRAWL_HOURS=0-23` in `.env` to populate immediately, then narrow it again.

On Windows, run the same commands **inside the WSL2 distro** (e.g.
`cd /mnt/d/.../deploy && docker compose up -d --build`).

```bash
docker compose ps             # status (init = Exited 0; rest = Up)
docker compose logs -f vndb   # tail a service
docker compose down [-v]      # stop (-v also wipes data volumes)
```

---

## 4. Advice — networking & proxy *(optional; only if you are behind a proxy or a restricted network)*

Routing Docker through a proxy (e.g. Clash on Windows `:7890`, WSL2 with
`networkingMode=mirrored`) splits into **three independent layers** — configure
only the ones you need. Addresses below assume mirrored networking, where the
WSL host's `127.0.0.1` maps to Windows (on NAT networking, use the host IP).

**1. Image pulls — the `dockerd` daemon.** A systemd service does not inherit your
shell environment, so the proxy must be set via a drop-in
`/etc/systemd/system/docker.service.d/http-proxy.conf`:

```ini
[Service]
Environment="HTTP_PROXY=http://127.0.0.1:7890"
Environment="HTTPS_PROXY=http://127.0.0.1:7890"
Environment="NO_PROXY=localhost,127.0.0.1,::1"
```
then `systemctl daemon-reload && systemctl restart docker`.

**2. Build-time downloads (apt/pip/npm).** `~/.docker/config.json` injects the proxy
into build steps; the build must also use **host networking**, because a build
container's `127.0.0.1` is its own loopback, not the host's:

```json
{ "proxies": { "default": {
    "httpProxy": "http://127.0.0.1:7890",
    "httpsProxy": "http://127.0.0.1:7890",
    "noProxy": "localhost,127.0.0.1,::1" } } }
```
plus `network: host` under each `build:` in `docker-compose.yml`.

**3. Runtime service outbound.** Keep services on the **bridge** network — chiefly
so Caddy stays the *only* exposed port (network isolation: just `:30709` is
published), and as a bonus service-name DNS (`vndb:5000`) keeps working. A bridge
container cannot reach the Windows loopback, so the proxy must be a **host-routable
address (the Windows LAN IP), not `127.0.0.1`**, with internal service names excluded:

```yaml
vndb:
  environment:
    HTTP_PROXY: http://<windows-LAN-IP>:7890
    HTTPS_PROXY: http://<windows-LAN-IP>:7890
    NO_PROXY: localhost,127.0.0.1,postgres,redis,transserve,imgserve,userserve,musicserve
```
This also requires Clash **"Allow LAN"** and a firewall rule for `7890`.

> You *can* instead run a service with `network_mode: host` — then `127.0.0.1:7890`
> reaches Clash directly (no LAN IP / Allow-LAN needed). **Not recommended:** host
> networking drops network isolation (every service binds the host directly — e.g.
> Postgres becomes reachable on the host/LAN, not just Caddy on `:30709`) and loses
> service-name DNS, so you'd have to rewrite inter-service addresses to `127.0.0.1:<port>`.

> **WSL2 / Postgres:** first-boot `initdb` can be slow (fsync). The Postgres
> healthcheck already allows a generous `start_period`; if it reports `unhealthy`
> right after a fresh recreate, wait ~1 min and re-run `docker compose up -d`.
