<#
.SYNOPSIS
    Trident Placement Agent — Developer Helper Script
    Usage: .\scripts\dev.ps1 <command>
    Commands: install, test, run, docker-up, docker-down, migrate, lint, check
#>

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("install", "test", "run", "docker-up", "docker-down", "migrate", "lint", "check")]
    [string]$Command
)

$Root = Split-Path -Parent $PSScriptRoot

switch ($Command) {
    "install" {
        Write-Host "Installing dependencies..." -ForegroundColor Cyan
        pip install -r "$Root\requirements.txt"
    }
    "test" {
        Write-Host "Running tests..." -ForegroundColor Cyan
        Set-Location $Root
        pytest tests/ -v
    }
    "run" {
        Write-Host "Starting server..." -ForegroundColor Cyan
        Set-Location $Root
        uvicorn main:app --reload --host 0.0.0.0 --port 8000
    }
    "docker-up" {
        Write-Host "Starting Docker services..." -ForegroundColor Cyan
        Set-Location $Root
        docker-compose up -d
        Write-Host "Agent running at http://localhost:8000/api/health" -ForegroundColor Green
    }
    "docker-down" {
        Write-Host "Stopping Docker services..." -ForegroundColor Cyan
        Set-Location $Root
        docker-compose down
    }
    "migrate" {
        Write-Host "Running database migrations..." -ForegroundColor Cyan
        Set-Location $Root
        alembic upgrade head
    }
    "lint" {
        Write-Host "Running syntax check on all .py files..." -ForegroundColor Cyan
        Get-ChildItem -Path $Root -Recurse -Filter "*.py" | ForEach-Object {
            $result = python -m py_compile $_.FullName 2>&1
            if ($result) {
                Write-Host "ERROR: $($_.FullName)" -ForegroundColor Red
                Write-Host $result -ForegroundColor Red
            } else {
                Write-Host "OK: $($_.Name)" -ForegroundColor Green
            }
        }
    }
    "check" {
        Write-Host "Checking health endpoint..." -ForegroundColor Cyan
        try {
            $resp = Invoke-RestMethod -Uri "http://localhost:8000/api/health" -Method GET
            Write-Host "Status: $($resp.status)" -ForegroundColor Green
            Write-Host "Timestamp: $($resp.timestamp)"
        } catch {
            Write-Host "Agent not reachable. Is it running?" -ForegroundColor Red
        }
    }
}
