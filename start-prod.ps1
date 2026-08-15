# ============================================================================
# Whole-app launcher. Boots three children and forwards Ctrl+C to all of them:
#   1. backend/launch.py via `pixi run` — Redis + Celery + the Flask servers,
#      inside the pixi env (run backend/scripts/pixi-setup.ps1 once first).
#   2. Next.js — the standalone server, or `next dev` under -Dev.
#   3. Caddy — the public ingress (frp forwards to -Bind, default :30709);
#      routes are in ./Caddyfile.snippet, upstreams from ./caddy-env.ps1.
#
# The edge lives here rather than in backend/launch.py because it fronts BOTH
# halves — routing /visual-novel-database to Next and /vndb, /imgserve, … to
# Flask. It is needed in dev too: `next dev`'s rewrites proxy the backend calls
# through it (see frontend/.env.local).
#
# Postgres is not spawned by anything — it runs as a Windows service
# (backend/scripts/pg-service.ps1). This script verifies it is up and accepting
# connections first, auto-starting the service if it is merely stopped.
#
# The frontend sits under a basePath rather than the origin root, so the same
# public port can front other apps too — run with -NoCaddy to let an external
# edge own the port instead.
#
# Usage:
#   .\start-prod.ps1                     # start with whatever is already built
#   .\start-prod.ps1 -Build              # `npm run build` first, then start
#   .\start-prod.ps1 -Dev                # dev stack (pixi run dev + next dev)
#   .\start-prod.ps1 -Clean              # delete frontend/.next first, then start
#   .\start-prod.ps1 -NoCaddy            # skip the edge (something else owns the port)
#   .\start-prod.ps1 -NextPort 5005      # override the Next.js port
#   .\start-prod.ps1 -Bind :8080         # override the public port
#   .\start-prod.ps1 -SkipPgCheck        # skip the Postgres readiness check
#   .\start-prod.ps1 -PgServiceName foo  # check a differently-named PG service
# ============================================================================

[CmdletBinding()]
param(
    [switch]$Build,
    # Dev stack: `pixi run dev` (Flask dev servers + Flower) plus `next dev`,
    # instead of Waitress + the Next.js standalone build. Caddy runs either way.
    [switch]$Dev,
    # Delete frontend/.next (old build output) before starting. In prod this
    # forces a fresh `npm run build`; in dev `next dev` recompiles from scratch.
    [switch]$Clean,
    # Override the Next.js port. Deliberately has no default here — caddy-env.ps1
    # holds the only one, so this script and the edge cannot disagree about it.
    [int]$NextPort,
    # The public port. frp forwards here.
    [string]$Bind = ':30709',
    # Skip this project's edge, for when an external one already owns the public
    # port. That edge is expected to import ./Caddyfile.snippet, so the routes are
    # identical; two Caddy processes just cannot both bind the port.
    [switch]$NoCaddy,
    # Postgres runs as a Windows service (backend/scripts/pg-service.ps1); this
    # is its service name (matches that script's default).
    [string]$PgServiceName = 'postgresql-vndb',
    # Bypass the Postgres check entirely — for when Postgres is run some other
    # way (different service name, container, remote host, etc.).
    [switch]$SkipPgCheck
)

$ErrorActionPreference = 'Stop'

$root             = $PSScriptRoot
$backendDir       = Join-Path $root 'backend'
$frontendDir      = Join-Path $root 'frontend'
$standaloneRoot   = Join-Path $frontendDir '.next\standalone'
$standaloneServer = Join-Path $standaloneRoot 'server.js'
# Dev mode runs `next dev` straight through node (same as the prod standalone
# server) rather than via npm/cmd, so Ctrl+C reaches it cleanly and taskkill /T
# can walk its tree on the backstop path.
$nextBin          = Join-Path $frontendDir 'node_modules\next\dist\bin\next'

# Pixi is required — we launch the backend through `pixi run` so it uses
# the env declared in backend/pixi.toml rather than whatever `python` on
# PATH happens to be. The env is materialized by backend/scripts/pixi-setup.ps1.
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    throw "pixi is not on PATH. Install it (scoop install pixi) and run backend\scripts\pixi-setup.ps1 once before start-prod.ps1."
}
if (-not (Test-Path (Join-Path $backendDir '.pixi'))) {
    Write-Host "[WARN] backend\.pixi not found — running backend\scripts\pixi-setup.ps1 to install the env." -ForegroundColor Yellow
    & (Join-Path $backendDir 'scripts\pixi-setup.ps1')
    if ($LASTEXITCODE -ne 0) { throw "backend\scripts\pixi-setup.ps1 failed (exit $LASTEXITCODE)" }
}

# ---------- edge preflight ---------------------------------------------------
# Checked up here, before any child is spawned: these throw, and the teardown
# handler is only installed further down — a failure after the backend and
# frontend were already running would orphan them, still holding their ports.
if (-not $NoCaddy) {
    if (-not (Get-Command caddy -ErrorAction SilentlyContinue)) {
        throw 'caddy is not on PATH (https://caddyserver.com/download), or pass -NoCaddy if another edge owns the port.'
    }
    # Any external edge fronting this app wants the same port, by design. Say so
    # plainly rather than letting Caddy fail to bind and bury the reason in its
    # JSON log.
    $bindPort = [int]($Bind -split ':')[-1]
    if (Get-NetTCPConnection -LocalPort $bindPort -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $bindPort is already in use — another edge, or an earlier run, owns it. Stop it first, or pass -NoCaddy."
    }
}

# ---------- Postgres preflight ----------------------------------------------
# launch.py does NOT launch Postgres; it expects the cluster to be up. The
# canonical way is the Windows service (backend/scripts/pg-service.ps1), but
# Postgres might equally be run another way (a differently-named service, a
# container, a foreground postmaster, a remote host). So reachability is the
# source of truth here: probe the port first, and only fall back to managing
# the named service when nothing is answering on it.
#
#   - port reachable                       -> proceed (warn if the managed
#                                             service looks abnormal, but a
#                                             reachable DB is all the children
#                                             actually need)
#   - port dead + service Stopped          -> auto-start the service, re-probe
#   - port dead + service missing/unstartable -> fail fast with guidance
#     (every Flask/Celery child would otherwise die on its first connect)

function Test-PgPortOpen {
    param([string]$TargetHost, [int]$Port, [int]$TimeoutMs = 1000)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $iar = $client.BeginConnect($TargetHost, $Port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne($TimeoutMs) -and $client.Connected) {
            $client.EndConnect($iar)
            return $true
        }
        return $false
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Resolve-PgHostPort {
    # Pull host:port out of VNDB_DB_URL in backend/.env so the readiness probe
    # hits the same cluster the app connects to. Defaults to localhost:5432.
    $result = @{ TargetHost = 'localhost'; Port = 5432 }
    $envFile = Join-Path $backendDir '.env'
    if (Test-Path $envFile) {
        foreach ($line in Get-Content $envFile) {
            if ($line -match '^\s*VNDB_DB_URL\s*=\s*(.+?)\s*$') {
                $url = $Matches[1].Trim().Trim('"').Trim("'")
                if ($url -match '@([^:/@]+):(\d+)/') {
                    $result.TargetHost = $Matches[1]
                    $result.Port = [int]$Matches[2]
                }
                break
            }
        }
    }
    return $result
}

function Ensure-Postgres {
    $pg = Resolve-PgHostPort
    $probeHost = if ($pg.TargetHost -in @('0.0.0.0', '::')) { 'localhost' } else { $pg.TargetHost }
    $svc = Get-Service -Name $PgServiceName -ErrorAction SilentlyContinue

    # 1. Reachability first — if the cluster already accepts connections we're
    #    done, regardless of how it's being run.
    Write-Host "[PG] Probing ${probeHost}:$($pg.Port) ..." -ForegroundColor Cyan
    if (Test-PgPortOpen -TargetHost $probeHost -Port $pg.Port) {
        if (-not $svc) {
            Write-Host "[PG] Reachable on ${probeHost}:$($pg.Port) (service '$PgServiceName' not registered — Postgres is running another way). Proceeding." -ForegroundColor Green
        } elseif ($svc.Status -ne 'Running') {
            Write-Host "[PG][WARN] Reachable on ${probeHost}:$($pg.Port), but the managed service '$PgServiceName' is '$($svc.Status)' — something else is serving this port. Proceeding anyway." -ForegroundColor Yellow
        } else {
            Write-Host "[PG] Reachable on ${probeHost}:$($pg.Port) (service '$PgServiceName' Running)." -ForegroundColor Green
        }
        return
    }

    # 2. Nothing answering on the port — fall back to the managed service.
    Write-Host "[PG] Not reachable; checking service '$PgServiceName'." -ForegroundColor Cyan
    if (-not $svc) {
        Write-Host "[PG][ERROR] Nothing listening on ${probeHost}:$($pg.Port) and service '$PgServiceName' is not registered." -ForegroundColor Red
        Write-Host "            Register it once from an elevated PowerShell:" -ForegroundColor Red
        Write-Host "              backend\scripts\pg-service.ps1 register" -ForegroundColor Red
        Write-Host "            Or pass -SkipPgCheck if you run Postgres another way." -ForegroundColor Red
        throw "PostgreSQL not reachable on ${probeHost}:$($pg.Port) and service '$PgServiceName' not found."
    }

    if ($svc.Status -ne 'Running') {
        Write-Host "[PG] Service is '$($svc.Status)'; attempting Start-Service ..." -ForegroundColor Yellow
        try {
            Start-Service -Name $PgServiceName -ErrorAction Stop
            (Get-Service -Name $PgServiceName).WaitForStatus('Running', '00:00:30')
            Write-Host "[PG] Service started." -ForegroundColor Green
        } catch {
            Write-Host "[PG][ERROR] Could not start '$PgServiceName': $($_.Exception.Message)" -ForegroundColor Red
            Write-Host "            Start it from an elevated PowerShell:" -ForegroundColor Red
            Write-Host "              backend\scripts\pg-service.ps1 start" -ForegroundColor Red
            throw "PostgreSQL service '$PgServiceName' is not running."
        }
    }

    # 3. Service is Running now (or already was) but the port wasn't answering
    #    a moment ago — a 'Running' service can briefly precede the postmaster
    #    accepting TCP connections, so re-probe with a short retry window.
    Write-Host "[PG] Waiting for ${probeHost}:$($pg.Port) to accept connections ..." -ForegroundColor Cyan
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        if (Test-PgPortOpen -TargetHost $probeHost -Port $pg.Port) {
            Write-Host "[PG] Accepting connections on ${probeHost}:$($pg.Port)." -ForegroundColor Green
            return
        }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "[PG][ERROR] '$PgServiceName' is Running but ${probeHost}:$($pg.Port) never accepted a connection within 30s." -ForegroundColor Red
    Write-Host "            Inspect the cluster: backend\scripts\pg-service.ps1 status" -ForegroundColor Red
    throw "PostgreSQL not accepting connections on ${probeHost}:$($pg.Port)."
}

if ($SkipPgCheck) {
    Write-Host "[PG] -SkipPgCheck set; skipping PostgreSQL service/readiness check." -ForegroundColor Yellow
} else {
    Ensure-Postgres
}

# ---------- optional clean step ---------------------------------------------
# Wipe the previous build output so a rebuild can't pick up stale chunks. In
# prod this makes a fresh build mandatory (forced below); in dev `next dev`
# simply recompiles into a clean .next.
if ($Clean) {
    $nextDir = Join-Path $frontendDir '.next'
    if (Test-Path $nextDir) {
        Write-Host "[CLEAN] Removing old build output: $nextDir" -ForegroundColor Cyan
        Remove-Item -Recurse -Force $nextDir
    } else {
        Write-Host "[CLEAN] No existing .next to remove." -ForegroundColor Cyan
    }
}

# ---------- resolve where everything listens ---------------------------------
# caddy-env.ps1 owns this: the Flask ports from backend/.env, the Next port from
# its own default. Read the Next port back out rather than defaulting it here, so
# the Next server and the edge cannot end up pointing at different ports.
$overrides = @{}
if ($NextPort) { $overrides.NextPort = $NextPort }

$caddyEnv = & (Join-Path $root 'caddy-env.ps1') @overrides
$caddyEnv.CADDY_BIND = $Bind

$NextPort = [int]($caddyEnv.NEXT_UPSTREAM -split ':')[-1]

# Use Start-Process for the children so we get real Process objects back and can
# Wait/Stop them individually. All inherit the console, so their stdout
# interleaves into this terminal.

$children = @()

function Stop-Children {
    # Ctrl+C is the graceful path: Windows fans CTRL_C_EVENT out to the whole
    # console process group, so launch.py runs its own ordered teardown. This is
    # the backstop for an external kill. taskkill /T walks the process tree — the
    # real workloads are grandchildren, which Stop-Process would orphan.
    foreach ($p in $children) {
        if ($p -and -not $p.HasExited) {
            Start-Process -FilePath 'taskkill' -ArgumentList @('/F', '/T', '/PID', $p.Id) `
                -NoNewWindow -Wait -ErrorAction SilentlyContinue | Out-Null
        }
    }
}

# Every spawn lives inside this try, so a failure part-way through tears down what
# already started instead of orphaning it, still holding its port.
try {
    if ($Dev) {
        # ======================= DEV STARTUP ===========================
        # Dev stack: `pixi run dev` (Flask dev servers + Flower) plus `next dev`. The
        # browser hits Next.js directly on :$NextPort; its rewrites
        # (frontend/next.config.ts, frontend/.env.local) proxy /vndb, /imgserve, … back
        # through Caddy, which is why the edge runs in dev too.
        if ($Build) {
            Write-Host "[WARN] -Build is ignored in -Dev mode; next dev compiles on demand." -ForegroundColor Yellow
        }
        if (-not (Test-Path $nextBin)) {
            throw "next CLI not found at $nextBin. Run 'npm install' in frontend/ first."
        }

        Write-Host "[START] backend/launch.py dev via pixi (Flask dev + Flower)" -ForegroundColor Green
        $backend = Start-Process `
            -FilePath 'pixi' `
            -ArgumentList @('run', 'dev') `
            -WorkingDirectory $backendDir `
            -NoNewWindow `
            -PassThru
        $children += $backend

        Write-Host "[START] Next.js dev server on http://127.0.0.1:$NextPort" -ForegroundColor Green
        # -H 127.0.0.1 to match what Caddy dials (see caddy-env.ps1). Without it, next
        # dev picks its own default host and the edge's frontend route can 502 in dev.
        $frontend = Start-Process `
            -FilePath 'node' `
            -ArgumentList @($nextBin, 'dev', '--port', $NextPort, '-H', '127.0.0.1') `
            -WorkingDirectory $frontendDir `
            -NoNewWindow `
            -PassThru
        $children += $frontend
    } else {
        # ========================== PROD STARTUP ================================
        # ---------- build step --------------------------------------------------
        # -Clean wiped .next, so a build is mandatory after it; -Build requests one
        # explicitly.
        if ($Build -or $Clean) {
            Write-Host "[BUILD] Running npm run build in frontend/" -ForegroundColor Cyan
            Push-Location $frontendDir
            try {
                npm run build
                if ($LASTEXITCODE -ne 0) { throw "npm run build failed (exit $LASTEXITCODE)" }
            } finally {
                Pop-Location
            }
        }

        if (-not (Test-Path $standaloneServer)) {
            throw "Standalone build not found at $standaloneServer. Run with -Build (or -Clean) first."
        }

        # ---------- mirror static + public into the standalone tree -------------
        # Next.js standalone emits a self-contained server.js but does NOT copy the
        # static asset folders. Without this sync, browser requests for
        # /_next/static/* return 404 and the SPA shows "This page couldn't load".
        #
        # Runs every launch (not just with -Build) so a manual `npm run build`
        # outside this script — or any rebuild that changes chunk filenames — is
        # always reflected in the standalone tree. The destination folders are
        # wiped first so old chunk filenames don't linger and shadow fresh ones.
        $srcStatic = Join-Path $frontendDir '.next\static'
        if (-not (Test-Path $srcStatic)) {
            throw "Source .next/static not found at $srcStatic. Run with -Build (or -Clean) first."
        }
        Write-Host "[SYNC] Mirroring .next/static and public into standalone tree" -ForegroundColor Cyan

        $destStatic = Join-Path $standaloneRoot '.next\static'
        if (Test-Path $destStatic) { Remove-Item -Recurse -Force $destStatic }
        Copy-Item -Recurse -Force $srcStatic $destStatic

        $srcPublic  = Join-Path $frontendDir 'public'
        $destPublic = Join-Path $standaloneRoot 'public'
        if (Test-Path $destPublic) { Remove-Item -Recurse -Force $destPublic }
        if (Test-Path $srcPublic) {
            Copy-Item -Recurse -Force $srcPublic $destPublic
        }

        # ---------- launch children ---------------------------------------------
        Write-Host "[START] backend/launch.py prod via pixi" -ForegroundColor Green
        $backend = Start-Process `
            -FilePath 'pixi' `
            -ArgumentList @('run', 'prod') `
            -WorkingDirectory $backendDir `
            -NoNewWindow `
            -PassThru
        $children += $backend

        Write-Host "[START] Next.js standalone on :$NextPort" -ForegroundColor Green
        # Start-Process doesn't take an env hashtable, so set process-scoped env
        # vars before launching and unset after — server.js reads PORT/HOSTNAME at
        # startup.
        $prevPort = $env:PORT; $prevHost = $env:HOSTNAME
        $env:PORT = "$NextPort"; $env:HOSTNAME = '127.0.0.1'
        try {
            $frontend = Start-Process `
                -FilePath 'node' `
                -ArgumentList @($standaloneServer) `
                -WorkingDirectory (Split-Path $standaloneServer) `
                -NoNewWindow `
                -PassThru
        } finally {
            $env:PORT = $prevPort; $env:HOSTNAME = $prevHost
        }
        $children += $frontend
    }

    # ---------- edge ----------------------------------------------------------
    # Caddy tolerates upstreams that are still coming up (502 until they answer),
    # so it needs no ordering against the children above.
    if ($NoCaddy) {
        Write-Host "[START] Caddy skipped (-NoCaddy); an external edge owns the port." -ForegroundColor Yellow
    } else {
        Write-Host "[START] Caddy on $Bind" -ForegroundColor Green
        $saved = @{}
        foreach ($key in $caddyEnv.Keys) {
            $saved[$key] = [Environment]::GetEnvironmentVariable($key, 'Process')
            [Environment]::SetEnvironmentVariable($key, [string]$caddyEnv[$key], 'Process')
        }
        try {
            $children += Start-Process `
                -FilePath 'caddy' `
                -ArgumentList @('run', '--config', (Join-Path $root 'Caddyfile'), '--adapter', 'caddyfile') `
                -WorkingDirectory $root `
                -NoNewWindow `
                -PassThru
        } finally {
            foreach ($key in $saved.Keys) {
                [Environment]::SetEnvironmentVariable($key, $saved[$key], 'Process')
            }
        }
    }

    # ---------- wait ----------------------------------------------------------
    # Stop as soon as ANY child dies: a surviving frontend and edge would serve a
    # broken site with nothing to say so.
    while ($true) {
        Start-Sleep -Seconds 1
        $dead = $children | Where-Object { $_.HasExited } | Select-Object -First 1
        if ($dead) {
            Write-Host "[EXIT] a child exited with $($dead.ExitCode); stopping the rest." -ForegroundColor Yellow
            break
        }
    }
} finally {
    Stop-Children
}
