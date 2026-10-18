# Setup Guide: Self-Hosted Runner & Local Execution

This guide explains how to set up an authorized local Windows environment or self-hosted GitHub Actions runner for the Trident Placement Automation monitor.

---

## Architecture Context & Execution Policy

- **No Proxies / Evasion**: In adherence to project constraints, automated monitoring operates without proxies, rotating IP pools, CAPTCHA bypasses, or WAF evasion tactics.
- **Fail-Closed on HTTP 403**: If the remote placement server returns an HTTP 403 Forbidden status, the fetcher immediately halts and logs the block with diagnostic details (`cf-ray` identifier) for review.
- **Recommended Environments**:
  1. **Local Windows Execution (Task Scheduler)** — Preferred for standard local automation.
  2. **Self-Hosted Runner (GitHub Actions)** — For centralized dispatch and execution from a dedicated local workstation or VM.

---

## Option 1: Local Windows Task Scheduler (Recommended)

You can run the monitor recurringly on your local Windows PC without needing GitHub Actions runner infrastructure:

1. Use the provided batch launcher [`run_monitor.bat`](../run_monitor.bat):
   ```cmd
   cd /d E:\tridentauto\placement-agent
   run_monitor.bat
   ```
2. Schedule it via Windows Task Scheduler:
   - Action: **Start a program**
   - Program/script: `cmd.exe`
   - Arguments: `/c E:\tridentauto\placement-agent\run_monitor.bat`
   - Trigger: Recurring every 30 minutes.

---

## Option 2: Self-Hosted Runner (Windows)

If you wish to trigger or schedule the monitoring workflow through GitHub Actions:

### Step-by-Step Setup

1. In your GitHub repository:
   - Go to **Settings** -> **Actions** -> **Runners** -> **New self-hosted runner**.
   - Select OS: **Windows**, Architecture: **x64**.
2. Run PowerShell as Administrator and configure the runner directory:
   ```powershell
   # Create runner folder
   mkdir C:\actions-runner; cd C:\actions-runner

   # Download runner package (use current download link from GitHub)
   Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/v2.322.0/actions-runner-win-x64-2.322.0.zip -OutFile actions-runner-win-x64-2.322.0.zip
   Expand-Archive -Path .\actions-runner-win-x64-2.322.0.zip -DestinationPath .

   # Configure runner with registration token from GitHub
   .\config.cmd --url https://github.com/<YOUR_USER>/<YOUR_REPO> --token <YOUR_REGISTRATION_TOKEN>
   ```
3. Run as a continuous Windows Service (auto-starts on boot):
   ```powershell
   .\svc.cmd install
   .\svc.cmd start
   ```
   Or run interactively in a console:
   ```powershell
   .\run.cmd
   ```

4. Once registered and marked `Idle`, the `monitor.yml` workflow will route jobs to this runner.
