# Setup Guide: Self-Hosted Runner & Proxy Solutions

This guide explains how to use both **Option 1 (Self-Hosted Runner)** and **Option 2 (Proxy)** to resolve HTTP 403 Forbidden errors caused by Cloudflare blocking GitHub Actions runner IPs.

---

## Option 1: Self-Hosted Runner (Recommended — Free & Reliable)

Because your local machine / home network in India is permitted with `200 OK` by Cloudflare, running jobs on a self-hosted runner bypasses all datacenter ASN and geographic IP blocks.

### Step-by-Step Setup (Windows)

1. Open your GitHub repository in your browser:
   `https://github.com/JeebanM/trident-placement-automation/settings/actions/runners/new?arch=x64&os=win`
2. Open PowerShell as Administrator on your PC and run the commands provided on that page:
   ```powershell
   # Create runner folder
   mkdir C:\actions-runner; cd C:\actions-runner

   # Download runner package (GitHub provides the latest link)
   Invoke-WebRequest -Uri https://github.com/actions/runner/releases/download/v2.322.0/actions-runner-win-x64-2.322.0.zip -OutFile actions-runner-win-x64-2.322.0.zip
   Expand-Archive -Path .\actions-runner-win-x64-2.322.0.zip -DestinationPath .

   # Configure runner (use your repository URL and registration token from GitHub)
   .\config.cmd --url https://github.com/JeebanM/trident-placement-automation --token <YOUR_REGISTRATION_TOKEN>
   ```
3. To run as a continuous Windows Service (auto-starts on boot):
   ```powershell
   .\svc.cmd install
   .\svc.cmd start
   ```
   Or run interactively in terminal:
   ```powershell
   .\run.cmd
   ```

Once connected, GitHub will mark the runner as `Idle` (ready). Every 30 minutes, your scheduled workflow will run directly on this runner without being blocked!

---

## Option 2: Proxy via GitHub Secrets (for `ubuntu-latest`)

If you want the workflow to run on GitHub's hosted `ubuntu-latest` cloud runners, route traffic through a residential or Indian proxy.

1. Obtain an HTTP or SOCKS5 proxy from an Indian / residential proxy provider (e.g. Webshare, BrightData, Oxylabs, or a self-hosted Tailscale exit node).
   Example format:
   `http://username:password@proxy-host.com:port`
2. In your GitHub repository:
   - Go to **Settings** -> **Secrets and variables** -> **Actions**.
   - Under **Repository secrets**, click **New repository secret**.
   - Name: `PROXY_URL` (or `HTTPS_PROXY`).
   - Value: `http://username:password@proxy-host.com:port`
3. If you want scheduled runs to use `ubuntu-latest` by default:
   - Go to **Settings** -> **Secrets and variables** -> **Actions** -> **Variables**.
   - Create a repository variable:
     - Name: `RUNNER_TYPE`
     - Value: `ubuntu-latest`

---

## Triggering Manually with Runner Selection

In GitHub Actions:
1. Go to the **Actions** tab.
2. Select **Trident Monitor Pipeline**.
3. Click **Run workflow**.
4. Choose the runner environment from the dropdown:
   - `self-hosted` (runs locally without proxy)
   - `ubuntu-latest` (runs on GitHub cloud using `PROXY_URL` if configured)
