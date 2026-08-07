import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
VENV = ROOT / ".venv"


class LocalSetupError(RuntimeError):
    pass


def executable(name: str) -> str:
    value = shutil.which(name)
    if not value:
        raise LocalSetupError(f"Missing {name}. Install it before running RuleMirror; this script never installs dependencies.")
    return value


def existing(path: Path, label: str) -> Path:
    if not path.exists():
        raise LocalSetupError(f"Missing {label} at {path}. Install project dependencies before running RuleMirror.")
    return path


def run(command: list[str], environment: dict[str, str] | None = None):
    subprocess.run(command, cwd=ROOT, env=environment, check=True)


def main() -> int:
    try:
        node = executable("node")
        npm = executable("npm")
        python = existing(VENV / "bin" / "python3", "Python virtual environment")
        alembic = existing(VENV / "bin" / "alembic", "Alembic executable")
        uvicorn = existing(VENV / "bin" / "uvicorn", "Uvicorn executable")
        existing(WEB / "node_modules" / ".bin" / "vite", "web dependencies")
        run([node, "--version"])
        run([str(python), "-c", "import alembic, fastapi, sqlalchemy, uvicorn"])
        run([npm, "--prefix", str(WEB), "run", "build"])
        run([str(alembic), "upgrade", "head"])
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT / "backend")
        run([str(uvicorn), "app.main:app", "--host", "127.0.0.1", "--port", "8000"], environment)
    except LocalSetupError as error:
        print(f"RuleMirror could not start: {error}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as error:
        print(f"RuleMirror stopped because a required command failed with exit code {error.returncode}.", file=sys.stderr)
        return error.returncode or 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
