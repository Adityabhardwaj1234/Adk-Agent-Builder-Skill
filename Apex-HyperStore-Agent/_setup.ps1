$ErrorActionPreference = "Stop"
$root  = "C:\Users\MY PC\OneDrive\Desktop\adk-agent-creator-skill"
$old   = Join-Path $root "adk_workspace"
$ws    = Join-Path $root "Apex-HyperStore-Agent"
$py    = Join-Path $ws ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $ws | Out-Null

# 1. preserve the API key: reformat to GOOGLE_API_KEY=<value> if it is a bare token
$envFile = Join-Path $ws ".env"
$raw = (Get-Content -Raw (Join-Path $old ".env")).Trim()
if ($raw -notmatch "(?m)^\s*GOOGLE_API_KEY\s*=") {
    if ($raw -match "(?m)^\s*GOOGLE_GENAI_USE_ENTERPRISE\s*=") { $lines = $raw }
    else { $lines = "GOOGLE_API_KEY=$raw" }
    Set-Content -Path $envFile -Value $lines -Encoding UTF8
    Write-Output "ENV_FORMATTED=GOOGLE_API_KEY=<preserved, value not shown>"
} else {
    Copy-Item (Join-Path $old ".env") $envFile -Force
    Write-Output "ENV_COPIED=already prefixed"
}

# 2. remove the half-installed venv from the old folder
if (Test-Path (Join-Path $old ".venv")) { Remove-Item (Join-Path $old ".venv") -Recurse -Force }
Move-Item (Join-Path $old "_setup.log") (Join-Path $ws "_setup.log") -Force -ErrorAction SilentlyContinue
Remove-Item $old -Recurse -Force -ErrorAction SilentlyContinue
Write-Output "OLD_WORKSPACE_REMOVED=$(-not (Test-Path $old))"

# 3. fresh venv + install (no `eval` extra: litellm exceeds the Windows 260-char path limit here)
if (-not (Test-Path $py)) { python -m venv (Join-Path $ws ".venv") }
& $py -m pip install --upgrade pip --quiet
& $py -m pip install "google-adk[db,mcp]" --no-cache-dir
& $py -c "import google.adk as a, sqlite3, aiosqlite; print('ADK_OK', a.__version__)"
