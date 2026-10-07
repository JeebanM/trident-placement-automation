<#
.SYNOPSIS
    Trident Placement Agent — First Run Setup Wizard
    Run this once to configure and start the agent.
    Usage: .\scripts\first_run.ps1
#>

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "   Trident Auto Placement Agent — First Run Wizard" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""

$Root = Split-Path -Parent $PSScriptRoot

# Step 1: Create .env from template
$EnvFile = Join-Path $Root ".env"
$EnvExample = Join-Path $Root ".env.example"

if (-not (Test-Path $EnvFile)) {
    Write-Host "Step 1: Creating .env configuration file..." -ForegroundColor Yellow
    Copy-Item $EnvExample $EnvFile
    Write-Host "  ✓ Created .env from .env.example" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Opening .env in Notepad — fill in your credentials, then save and close." -ForegroundColor White
    Write-Host "  Required fields:" -ForegroundColor White
    Write-Host "    DATABASE_URL    — PostgreSQL connection string" -ForegroundColor Gray
    Write-Host "    GEMINI_API_KEY  — From Google AI Studio (aistudio.google.com)" -ForegroundColor Gray
    Write-Host "    GMAIL_APP_PASSWORD — 16-char App Password from myaccount.google.com/apppasswords" -ForegroundColor Gray
    Write-Host ""
    Start-Process notepad.exe -ArgumentList $EnvFile -Wait
} else {
    Write-Host "Step 1: .env already exists — skipping." -ForegroundColor Green
}

# Step 2: Validate setup
Write-Host ""
Write-Host "Step 2: Validating setup..." -ForegroundColor Yellow
Set-Location $Root
python scripts\check_setup.py
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "  ✗ Setup validation failed. Fix the issues above and re-run this script." -ForegroundColor Red
    exit 1
}

# Step 3: Choose deployment method
Write-Host ""
Write-Host "Step 3: How would you like to run the agent?" -ForegroundColor Yellow
Write-Host "  [1] Docker Compose (recommended — includes PostgreSQL)" -ForegroundColor White
Write-Host "  [2] Direct Python (you manage PostgreSQL separately)" -ForegroundColor White
Write-Host ""
$choice = Read-Host "Enter choice (1 or 2)"

if ($choice -eq "1") {
    Write-Host ""
    Write-Host "Starting with Docker Compose..." -ForegroundColor Cyan
    docker-compose up -d
    Write-Host ""
    Write-Host "Waiting for agent to start (15 seconds)..." -ForegroundColor Gray
    Start-Sleep -Seconds 15
    
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/api/health" -TimeoutSec 10
        Write-Host "  ✓ Agent is running! Status: $($health.status)" -ForegroundColor Green
    } catch {
        Write-Host "  ⚠ Agent may still be starting. Check: docker-compose logs agent" -ForegroundColor Yellow
    }
    
    Write-Host ""
    Write-Host "Triggering first pipeline run..." -ForegroundColor Cyan
    try {
        $result = Invoke-RestMethod -Uri "http://localhost:8000/api/run-now" -Method POST -TimeoutSec 120
        Write-Host "  ✓ First run complete!" -ForegroundColor Green
        Write-Host "  Posts found : $($result.total)" -ForegroundColor White
        Write-Host "  New posts   : $($result.new)" -ForegroundColor White
    } catch {
        Write-Host "  Pipeline triggered (running in background)" -ForegroundColor Yellow
    }
    
} elseif ($choice -eq "2") {
    Write-Host ""
    Write-Host "Starting directly with uvicorn..." -ForegroundColor Cyan
    Write-Host "  Make sure PostgreSQL is running and DATABASE_URL is correct." -ForegroundColor Yellow
    Write-Host ""
    uvicorn main:app --host 0.0.0.0 --port 8000
}

Write-Host ""
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "  Dashboard : http://localhost:8000/api/posts" -ForegroundColor Green
Write-Host "  Health    : http://localhost:8000/api/health" -ForegroundColor Green
Write-Host "  Manual run: curl -X POST http://localhost:8000/api/run-now" -ForegroundColor Green
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host ""
