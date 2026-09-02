# The environment Caddyfile.snippet expands, derived from this project's own
# config. Returns a hashtable.
#
# Owned here, not by the callers, so every edge agrees on where this app listens:
# start-prod.ps1 and any external edge source this file rather than restating
# ports. backend/.env stays the authority for the Flask ports — the only thing
# that actually decides where they bind.

[CmdletBinding()]
param(
    # The frontend has no config file of its own to bind from, so its default lives
    # here — the one place both edges already consult. start-prod.ps1 takes it from
    # here rather than declaring its own, so the two cannot drift apart.
    [int]$NextPort = $(if ($env:NEXT_PORT) { [int]$env:NEXT_PORT } else { 5010 })
)

$backendDir = Join-Path $PSScriptRoot 'backend'

function Read-DotEnv([string]$Path) {
    $result = @{}
    if (Test-Path $Path) {
        foreach ($line in Get-Content -LiteralPath $Path) {
            if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$') {
                $result[$Matches[1]] = $Matches[2].Trim('"').Trim("'")
            }
        }
    }
    return $result
}

$dotenv = Read-DotEnv (Join-Path $backendDir '.env')

# 127.0.0.1, not localhost: on Windows localhost resolves to ::1 first, and every
# cold connection to an IPv4-only listener would eat a ~20s IPv6 timeout.
$vars = @{ NEXT_UPSTREAM = "127.0.0.1:$NextPort" }

# Keyed by the service's own name, which is also the prefix its port variable
# carries in backend/.env and the one Caddyfile.snippet expands — VNDBSERVE_PORT
# feeding VNDBSERVE_UPSTREAM. (It used to say VNDB here, so the snippet's
# {$VNDBSERVE_UPSTREAM} silently fell through to its default and only worked
# because the default matched.)
#
# The environment outranks .env: each Flask app reads {NAME}_PORT from its own
# environment and python-dotenv does not overwrite what is already there, so a
# caller that places the ports (app-gateway does, so it can guarantee no two apps
# collide) is obeyed by this edge as well as by the services.
$defaults = @{ VNDBSERVE = 5000; IMGSERVE = 5001; USERSERVE = 5002
               TRANSSERVE = 5003; MUSICSERVE = 5004 }
foreach ($app in $defaults.GetEnumerator()) {
    $name = "$($app.Key)_PORT"
    $port = if ([Environment]::GetEnvironmentVariable($name)) { [Environment]::GetEnvironmentVariable($name) }
            elseif ($dotenv[$name])                          { $dotenv[$name] }
            else                                             { $app.Value }
    $vars["$($app.Key)_UPSTREAM"] = "127.0.0.1:$port"
}

# imgserve's image cache, which Caddy serves hits from directly. DATA_FOLDER is
# relative to backend/ — launch.py resolves it from there, its own working dir.
#
# Created here because Caddy's file matcher roots at it: imgserve only makes the
# directory lazily, on its first image download, so on a fresh checkout Caddy would
# otherwise start with a root that does not exist.
$dataFolder = if ($dotenv.DATA_FOLDER) { $dotenv.DATA_FOLDER } else { '../data' }
$imageFolder = [IO.Path]::GetFullPath(
    (Join-Path $backendDir (Join-Path $dataFolder 'images')))
New-Item -ItemType Directory -Path $imageFolder -Force | Out-Null

$vars.IMGSERVE_IMAGE_FOLDER = $imageFolder

# The OpenAPI specs and their browser, served from the repo so /docs always shows
# the checked-in version — nothing to rebuild or copy after editing a spec.
$vars.API_DOCS_FOLDER = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot 'docs/api'))

return $vars
