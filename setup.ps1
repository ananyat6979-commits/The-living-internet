# One-time setup for Windows PowerShell. Run from the repo root (the folder that contains "site" and "pipeline"):
#     .\setup.ps1
# If PowerShell blocks scripts:   Set-ExecutionPolicy -Scope Process Bypass
$ErrorActionPreference = "Stop"

if (-not (Test-Path "site\package.json")) {
  throw "Run this from the repo root, the folder that contains 'site' and 'pipeline'. You are in: $PWD"
}

# Tested on Python 3.10, 3.11, 3.12 and 3.13. Pick the newest one installed; never fall back to a random one.
function Test-Python([string[]]$Cmd) {
  try {
    $exe = $Cmd[0]
    $rest = @()
    if ($Cmd.Length -gt 1) { $rest = $Cmd[1..($Cmd.Length - 1)] }
    & $exe @rest -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,13) else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
  } catch { return $false }
}

$candidates = @(@("py","-3.13"), @("py","-3.12"), @("py","-3.11"), @("py","-3.10"), @("python"))
$chosen = $null
foreach ($c in $candidates) { if (Test-Python $c) { $chosen = $c; break } }
if (-not $chosen) {
  throw "No Python 3.10 to 3.13 found. Install one from https://www.python.org/downloads/ (tick 'Add to PATH'), then run this again."
}
Write-Host ("Using: " + ($chosen -join " "))

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "Creating virtual environment .venv"
  $rest = @()
  if ($chosen.Length -gt 1) { $rest = $chosen[1..($chosen.Length - 1)] }
  & $chosen[0] @rest -m venv .venv
  if ($LASTEXITCODE -ne 0) { throw "Could not create .venv" }
}
$venvPy = Join-Path $PWD ".venv\Scripts\python.exe"

# Always install with the venv's own python, so nothing ever lands in your global Python.
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
& $venvPy -c "import duckdb, pyarrow; print('duckdb', duckdb.__version__, 'pyarrow', pyarrow.__version__)"

Write-Host "Installing site packages (inside site\)"
npm --prefix site ci
if ($LASTEXITCODE -ne 0) { throw "npm ci failed. Is Node 18+ installed?  node --version" }

Write-Host "Creating SYNTHETIC demo data with the real pipeline"
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"   # so the npm script finds this venv's python
npm --prefix site run demo
if ($LASTEXITCODE -ne 0) { throw "demo data failed" }

Write-Host ""
Write-Host "Done. To run the site, in this same folder:"
Write-Host "    .\.venv\Scripts\Activate.ps1"
Write-Host "    npm run dev"
Write-Host "then open http://localhost:5173"
