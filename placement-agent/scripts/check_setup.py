"""
scripts/check_setup.py
──────────────────────
Standalone environment validation script for Trident Auto Placement Agent.
Checks Python version, dependencies, configuration, credentials, and network connectivity.
Run with: python scripts/check_setup.py
"""
import importlib
import os
from pathlib import Path
import sys
import urllib.request

# Optional colored output
try:
    import colorama
    colorama.init(autoreset=True)
    GREEN = colorama.Fore.GREEN
    YELLOW = colorama.Fore.YELLOW
    RED = colorama.Fore.RED
    CYAN = colorama.Fore.CYAN
    BOLD = colorama.Style.BRIGHT
    RESET = colorama.Style.RESET_ALL
except Exception:
    GREEN = YELLOW = RED = CYAN = BOLD = RESET = ""

passed_count = 0
warn_count = 0
fail_count = 0


def log_ok(title: str, detail: str = "") -> None:
    global passed_count
    passed_count += 1
    detail_str = f" - {detail}" if detail else ""
    print(f"[{GREEN}OK{RESET}] {title}{detail_str}")


def log_warn(title: str, detail: str = "") -> None:
    global warn_count
    warn_count += 1
    detail_str = f" - {detail}" if detail else ""
    print(f"[{YELLOW}WARN{RESET}] {title}{detail_str}")


def log_fail(title: str, detail: str = "") -> None:
    global fail_count
    fail_count += 1
    detail_str = f" - {detail}" if detail else ""
    print(f"[{RED}FAIL{RESET}] {title}{detail_str}")


def main() -> int:
    print(f"\n{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    print(f"{BOLD}🔍 Trident Auto Placement Agent — Preflight Check{RESET}")
    print(f"{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}\n")

    root_dir = Path(__file__).resolve().parent.parent

    # 1. Python version (3.11+)
    py_major, py_minor = sys.version_info.major, sys.version_info.minor
    py_version_str = f"{py_major}.{py_minor}.{sys.version_info.micro}"
    if (py_major, py_minor) >= (3, 11):
        log_ok("Python Version", f"v{py_version_str} (3.11+ required)")
    else:
        log_fail("Python Version", f"v{py_version_str} is below required 3.11+")

    # 2. Required packages
    required_packages = [
        ("httpx", "httpx"),
        ("bs4", "beautifulsoup4"),
        ("fitz", "PyMuPDF"),
        ("openpyxl", "openpyxl"),
        ("google.generativeai", "google-generativeai"),
        ("pydantic", "pydantic"),
        ("sqlalchemy", "SQLAlchemy"),
        ("apscheduler", "APScheduler"),
        ("structlog", "structlog"),
        ("yaml", "PyYAML"),
        ("fastapi", "fastapi"),
        ("uvicorn", "uvicorn"),
        ("alembic", "alembic"),
    ]

    for mod_name, pkg_name in required_packages:
        try:
            importlib.import_module(mod_name)
            log_ok(f"Package '{pkg_name}'")
        except ImportError:
            log_fail(f"Package '{pkg_name}'", f"missing, install via requirements.txt")

    # Load .env file if available
    env_file = root_dir / ".env"
    if env_file.is_file():
        log_ok(".env File", f"found at {env_file.name}")
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
        except ImportError:
            # Fallback naive .env parser
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    else:
        log_warn(".env File", "not found at root (acceptable if running in container with env_file)")

    # 4. Environment variables
    required_env_vars = [
        "DATABASE_URL",
        "GEMINI_API_KEY",
        "GMAIL_SENDER",
        "GMAIL_APP_PASSWORD",
        "GMAIL_RECIPIENT",
    ]

    for var in required_env_vars:
        val = os.environ.get(var)
        if val and val.strip():
            # Mask secrets in output
            if "PASSWORD" in var or "KEY" in var:
                masked = val[:4] + "..." + val[-2:] if len(val) > 6 else "***"
                log_ok(f"Environment variable {var}", f"set ({masked})")
            else:
                log_ok(f"Environment variable {var}", f"set ({val})")
        else:
            log_fail(f"Environment variable {var}", "missing or empty")

    # 5. Gmail credentials format
    gmail_app_pw = os.environ.get("GMAIL_APP_PASSWORD", "")
    if gmail_app_pw:
        clean_pw = gmail_app_pw.replace(" ", "")
        if len(gmail_app_pw) == 16 and " " not in gmail_app_pw:
            log_ok("Gmail App Password format", "valid 16-character string")
        elif len(gmail_app_pw) == 19 and len(clean_pw) == 16:
            log_ok("Gmail App Password format", "valid 16-character string with spaces")
        else:
            log_warn(
                "Gmail App Password format",
                f"length is {len(gmail_app_pw)} chars (expected 16-char Google App Password)",
            )

    # 6. DATABASE_URL format
    db_url = os.environ.get("DATABASE_URL", "")
    if db_url:
        if db_url.startswith("postgresql+asyncpg://"):
            log_ok("DATABASE_URL Scheme", "valid asyncpg scheme (postgresql+asyncpg://)")
        else:
            log_fail(
                "DATABASE_URL Scheme",
                f"must start with 'postgresql+asyncpg://' (found '{db_url.split('://')[0]}://')",
            )

    # 7. candidate.yaml
    candidate_yaml_path = root_dir / "candidate.yaml"
    if candidate_yaml_path.is_file():
        try:
            import yaml
            with open(candidate_yaml_path, "r", encoding="utf-8") as f:
                cand_data = yaml.safe_load(f)
            candidate = cand_data.get("candidate", {})
            name = candidate.get("name", "Unknown")
            branch = candidate.get("branch", [])
            grad_year = candidate.get("graduation_year", "Unknown")
            cgpa = candidate.get("cgpa", "Unknown")
            branch_str = ", ".join(branch) if isinstance(branch, list) else str(branch)

            log_ok(
                "candidate.yaml",
                f"Profile: {name} | Grad: {grad_year} | CGPA: {cgpa} | Branches: [{branch_str}]",
            )
        except Exception as e:
            log_fail("candidate.yaml", f"failed to parse: {str(e)}")
    else:
        log_fail("candidate.yaml", f"missing file at {candidate_yaml_path}")

    # 8. Network connectivity
    try:
        req = urllib.request.Request(
            "https://trident.ac.in",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                log_ok("Network Connectivity", "trident.ac.in is reachable (HTTP 200)")
            else:
                log_warn("Network Connectivity", f"trident.ac.in returned HTTP {resp.status}")
    except Exception as e:
        log_warn("Network Connectivity", f"could not reach trident.ac.in: {str(e)}")

    # Summary
    print(f"\n{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}")
    print(f"✅  {passed_count} checks passed")
    if warn_count > 0:
        print(f"⚠️   {warn_count} warnings")
    if fail_count > 0:
        print(f"❌  {fail_count} checks failed")
    print(f"{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}\n")

    if fail_count > 0:
        print(f"{RED}{BOLD}Fix the above issues before running the agent.{RESET}\n")
        return 1
    else:
        print(f"{GREEN}{BOLD}Setup looks good! Run: uvicorn main:app --reload{RESET}\n")
        return 0


if __name__ == "__main__":
    sys.exit(main())
