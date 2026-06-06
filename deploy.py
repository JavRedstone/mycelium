# Copyright 2026 Javier Huang
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Mycelium deployment script.

Usage (from the mycelium/ directory):
    uv run deploy.py                 # backend (Cloud Run) + frontend (Vercel)
    uv run deploy.py backend         # Cloud Run only
    uv run deploy.py frontend        # Vercel only
    uv run deploy.py agent           # Vertex AI Agent Engine only

Prerequisites:
    gcloud CLI    https://cloud.google.com/sdk/docs/install
    Docker Desktop running
    Vercel CLI    npm i -g vercel
    mycelium/.env filled in (copy from mycelium/.env.example)
"""
from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

_SHELL = platform.system() == "Windows"

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE     = Path(__file__).resolve().parent        # mycelium/  (repo root)
BACKEND  = HERE / "mycelium"                      # mycelium/mycelium/
FRONTEND = HERE / "mycelium-ui"                   # mycelium/mycelium-ui/
ENV_FILE = BACKEND / ".env"
URL_FILE = HERE / ".backend-url"


# ── Helpers ───────────────────────────────────────────────────────────────────

def run(*cmd: str, cwd: Path | None = None) -> None:
    print(f"  $ {' '.join(cmd)}")
    # shell=True required on Windows so .cmd tools (gcloud, vercel) are found
    result = subprocess.run(cmd, cwd=cwd, shell=_SHELL)
    if result.returncode != 0:
        _fail(f"Command failed: {' '.join(cmd)}")


def capture(*cmd: str) -> str:
    return subprocess.check_output(cmd, shell=_SHELL).decode().strip()


def load_env() -> dict[str, str]:
    if not ENV_FILE.exists():
        _fail(f"{ENV_FILE} not found\n  Copy mycelium/.env.example → mycelium/.env and fill in values")
    env = {k: v for k, v in dotenv_values(ENV_FILE).items() if v}
    for key in ("GOOGLE_CLOUD_PROJECT", "GITLAB_TOKEN", "GITLAB_PROJECT_ID", "MONGODB_URI"):
        if key not in env:
            _fail(f"{key} not set in mycelium/.env")
    env.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
    env.setdefault("GEMINI_MODEL",           "gemini-2.5-flash")
    env.setdefault("MONGODB_DB",             "mycelium")
    env.setdefault("GITLAB_URL",             "https://gitlab.com")
    env.setdefault("DEMO_MODE",              "false")
    return env


def _section(title: str) -> None:
    print(f"\n── {title} {'─' * (58 - len(title))}")

def _step(msg: str) -> None: print(f"\n▸ {msg}")
def _ok(msg: str)   -> None: print(f"\n✓ {msg}")
def _fail(msg: str) -> None:
    print(f"\n[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


# ── Targets ───────────────────────────────────────────────────────────────────

def deploy_backend(env: dict[str, str]) -> str:
    project = env["GOOGLE_CLOUD_PROJECT"]
    region  = env["GOOGLE_CLOUD_LOCATION"]
    service = "mycelium-api"
    image   = f"gcr.io/{project}/{service}"

    _section("Backend → Cloud Run")
    print(f"  Project : {project}")
    print(f"  Region  : {region}")
    print(f"  Image   : {image}")

    _step("Authenticating Docker with GCR...")
    run("gcloud", "auth", "configure-docker", "--quiet")

    _step("Building Docker image...")
    run("docker", "build", "-t", service, str(BACKEND))

    _step("Pushing to Container Registry...")
    run("docker", "tag", service, image)
    run("docker", "push", image)

    _step("Deploying to Cloud Run...")
    env_vars = ",".join([
        f"GOOGLE_CLOUD_PROJECT={project}",
        f"GOOGLE_CLOUD_LOCATION={region}",
        f"GEMINI_MODEL={env['GEMINI_MODEL']}",
        f"MONGODB_URI={env['MONGODB_URI']}",
        f"MONGODB_DB={env['MONGODB_DB']}",
        f"GITLAB_URL={env['GITLAB_URL']}",
        f"GITLAB_TOKEN={env['GITLAB_TOKEN']}",
        f"GITLAB_PROJECT_ID={env['GITLAB_PROJECT_ID']}",
        f"DEMO_MODE={env['DEMO_MODE']}",
        f"GITLAB_BOT_USERNAME={env.get('GITLAB_BOT_USERNAME', 'mycelium-bot')}",
        "CORS_ORIGINS=*",
        f"GITLAB_WEBHOOK_SIGNING_TOKEN={env.get('GITLAB_WEBHOOK_SIGNING_TOKEN', '')}",
        "GOOGLE_GENAI_USE_VERTEXAI=True",
    ])
    run(
        "gcloud", "run", "deploy", service,
        "--image",    image,
        "--region",   region,
        "--platform", "managed",
        "--allow-unauthenticated",
        "--port",     "8080",
        "--memory",   "2Gi",
        "--cpu",      "2",
        "--timeout",  "3600",
        "--set-env-vars", env_vars,
    )

    url = capture(
        "gcloud", "run", "services", "describe", service,
        "--region", region,
        "--format", "value(status.url)",
    )
    URL_FILE.write_text(url)
    _ok(f"Backend deployed: {url}")
    return url


def deploy_frontend(backend_url: str | None = None) -> None:
    _section("Frontend → Vercel")

    if not backend_url:
        backend_url = URL_FILE.read_text().strip() if URL_FILE.exists() else \
            input("  Backend URL (run 'uv run deploy.py backend' first): ").strip()

    print(f"  Backend URL: {backend_url}")

    (FRONTEND / ".env.production").write_text(
        f"NEXT_PUBLIC_API_URL={backend_url}\n"
        f"API_URL={backend_url}\n"
    )

    _step("Deploying to Vercel...")
    run("vercel", "--prod", "--yes", cwd=FRONTEND)
    _ok("Frontend deployed — check Vercel dashboard for the public URL")


def deploy_agent(env: dict[str, str]) -> None:
    _section("Agent → Vertex AI Agent Engine")
    if "GOOGLE_CLOUD_STORAGE_BUCKET" not in env:
        _fail("GOOGLE_CLOUD_STORAGE_BUCKET not set in .env (required for staging)")

    run(sys.executable, str(BACKEND / "deployment" / "deploy.py"), "--create", cwd=str(BACKEND))
    _ok("Agent Engine deployment complete")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else "all"

    if target not in ("all", "backend", "frontend", "agent"):
        print(__doc__)
        sys.exit(1)

    env = load_env()

    if target == "backend":
        deploy_backend(env)

    elif target == "frontend":
        deploy_frontend()

    elif target == "agent":
        deploy_agent(env)

    elif target == "all":
        url = deploy_backend(env)
        deploy_frontend(url)
        print(f"\n{'═' * 60}")
        print("  Deployment complete!")
        print(f"  Backend:  {url}")
        print("  Frontend: check Vercel dashboard")
        print(f"{'═' * 60}")


if __name__ == "__main__":
    main()
