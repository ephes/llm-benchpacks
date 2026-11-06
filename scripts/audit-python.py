"""Audit the frozen runtime/dev graph for the invoking Python interpreter."""

from pathlib import Path
import subprocess
import sys
import tempfile


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="benchpack-audit-") as directory:
        requirements = Path(directory) / "requirements.txt"
        subprocess.run(
            [
                "uv", "export", "--frozen", "--group", "dev",
                "--no-emit-project", "--format", "requirements-txt",
                "--output-file", str(requirements),
            ],
            cwd=root,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        subprocess.run(
            [
                "uvx", "--python", sys.executable, "pip-audit==2.10.1",
                "--require-hashes", "--disable-pip", "--strict",
                "--cache-dir", str(Path(directory) / "cache"),
                "--requirement", str(requirements),
            ],
            cwd=root,
            check=True,
        )


if __name__ == "__main__":
    main()
