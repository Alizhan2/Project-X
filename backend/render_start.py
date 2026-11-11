"""Temporary Render Free demo: one supervised web/worker container, no external supervisor dependency."""
import hashlib
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

BACKEND = Path(__file__).resolve().parent
# shortcut: web idle sleep pauses the cohosted worker; use an always-on worker beyond this short study.


def render_environment(source):
    """Translate Render's public origin and managed database settings without printing secrets."""
    result = dict(source)
    hostname = result.get("RENDER_EXTERNAL_HOSTNAME", "")
    if not hostname or len(hostname) > 253 or not all(
        re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
        for label in hostname.split(".")
    ) or "." not in hostname:
        raise ValueError("RENDER_EXTERNAL_HOSTNAME must be an exact public DNS hostname.")
    try:
        port = int(result.get("PORT", "10000"))
        if not 1 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise ValueError("PORT must be a valid TCP port.") from None

    if not result.get("DJANGO_SECRET_KEY"):
        seed = result.get("DOEDU_SECRET_SEED", "")
        if len(seed) < 32:
            raise ValueError("Provide DJANGO_SECRET_KEY or a generated DOEDU_SECRET_SEED of at least 32 characters.")
        result["DJANGO_SECRET_KEY"] = hashlib.sha512(b"Doedu Render demo Django secret v1\0" + seed.encode()).hexdigest()

    defaults = {
        "DOEDU_ENV": "production", "DOEDU_LAUNCH_MODE": "demo", "DJANGO_DEBUG": "false",
        "DJANGO_SECURE_SSL": "true", "DJANGO_ALLOWED_HOSTS": f"{hostname},127.0.0.1",
        "DJANGO_CSRF_TRUSTED_ORIGINS": f"https://{hostname}", "PUBLIC_APP_URL": f"https://{hostname}",
        "DOEDU_TRUSTED_PROXIES": "1", "GUNICORN_FORWARDED_ALLOW_IPS": "*",
        "GUNICORN_BIND": f"0.0.0.0:{port}", "WEB_CONCURRENCY": "1", "GUNICORN_THREADS": "4",
    }
    for key, value in defaults.items():
        result.setdefault(key, value)
    if result.get("DOEDU_RELEASE", "unknown") in ("unknown", "dev") and result.get("RENDER_GIT_COMMIT"):
        result["DOEDU_RELEASE"] = result["RENDER_GIT_COMMIT"][:12]
    return result


def supervise(environment):
    """Stop both process groups on shutdown or failure; Render owns restarting the container."""
    children = []
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGINT)}
    try:
        commands = [
            [sys.executable, "-m", "gunicorn", "config.wsgi:application", "-c", "gunicorn.conf.py"],
            [sys.executable, "manage.py", "run_worker"],
        ]
        for command in commands:
            if stopping:
                break
            children.append(subprocess.Popen(command, cwd=BACKEND, env=environment, start_new_session=True))
        while not stopping:
            if any(child.poll() is not None for child in children):
                print("A demo service exited; stopping its sibling so the platform can restart both.", file=sys.stderr)
                return 1
            time.sleep(0.25)
        return 0
    finally:
        for child in children:
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for child in children:
            try:
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                child.wait(timeout=5)
        for sig, handler in previous.items():
            signal.signal(sig, handler)


def main():
    try:
        environment = render_environment(os.environ)
        commands = [[sys.executable, "manage.py", "safe_migrate"]]
        if environment.get("DOEDU_BOOTSTRAP_DEMO", "").lower() in ("1", "true", "yes", "on"):
            commands.append([sys.executable, "manage.py", "bootstrap_hosted_demo"])
        for command in commands:
            subprocess.run(command, cwd=BACKEND, env=environment, check=True)
        return supervise(environment)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, subprocess.CalledProcessError):
        print("Hosted demo startup failed. Inspect the preceding service diagnostics.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
