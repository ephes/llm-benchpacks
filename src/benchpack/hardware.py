"""Best-effort hardware metadata and resource sampling.

Per ``docs/architecture.md`` "Hardware Metadata" the collector must never block
a run; missing values are recorded as ``None``.

macOS uses ``sysctl`` and ``system_profiler``.  Linux uses ``lscpu``,
``free``, ``nvidia-smi`` (when present), and ``/etc/os-release``.
"""

from __future__ import annotations

import platform
import socket
import subprocess
from pathlib import Path
from typing import Any


def _run(cmd: list[str], timeout: float = 5.0) -> str | None:
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout


def _sysctl(key: str) -> str | None:
    out = _run(["sysctl", "-n", key])
    return out.strip() if out else None


def _read_file(path: Path) -> str | None:
    try:
        return path.read_text()
    except OSError:
        return None


def _parse_os_release(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        fields[key.strip()] = value.strip().strip('"')
    return fields


def _parse_memory_mb(value: str) -> int | None:
    parts = value.strip().split()
    if len(parts) < 2:
        return None
    try:
        amount = float(parts[0])
    except ValueError:
        return None
    unit = parts[1].lower()
    if unit.startswith("tb"):
        return int(amount * 1024 * 1024)
    if unit.startswith("gb"):
        return int(amount * 1024)
    if unit.startswith("mb"):
        return int(amount)
    return None


def _parse_system_profiler_hardware(text: str) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "hardware_model_name": None,
        "hardware_model_identifier": None,
        "chip": None,
        "cpu_count": None,
        "ram_mb": None,
    }
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        value = value.strip()
        if key == "Model Name":
            fields["hardware_model_name"] = value or None
        elif key == "Model Identifier":
            fields["hardware_model_identifier"] = value or None
        elif key == "Chip":
            fields["chip"] = value or None
        elif key == "Total Number of Cores":
            first, *_ = value.split()
            if first.isdigit():
                fields["cpu_count"] = int(first)
        elif key == "Memory":
            fields["ram_mb"] = _parse_memory_mb(value)
    return fields


def _apple_cpu_model_is_unhelpful(value: str | None) -> bool:
    if not value:
        return True
    normalized = value.strip().lower()
    return normalized in {"apple processor", "apple"}


def _collect_macos() -> dict[str, Any]:
    cpu_model = _sysctl("machdep.cpu.brand_string")
    cpu_count_raw = _sysctl("hw.ncpu")
    ram_raw = _sysctl("hw.memsize")
    hardware_model = _sysctl("hw.model")
    chip_raw = cpu_model  # usually includes the Apple chip name
    cpu_count = int(cpu_count_raw) if cpu_count_raw and cpu_count_raw.isdigit() else None
    ram_mb = int(ram_raw) // (1024 * 1024) if ram_raw and ram_raw.isdigit() else None

    sp_hardware = _run(["system_profiler", "SPHardwareDataType"], timeout=10.0)
    sp_fields = _parse_system_profiler_hardware(sp_hardware) if sp_hardware else {}
    sp_chip = sp_fields.get("chip")
    if _apple_cpu_model_is_unhelpful(cpu_model) and sp_chip:
        cpu_model = sp_chip
    if not chip_raw or _apple_cpu_model_is_unhelpful(chip_raw):
        chip_raw = sp_chip
    if cpu_count is None:
        cpu_count = sp_fields.get("cpu_count")
    if ram_mb is None:
        ram_mb = sp_fields.get("ram_mb")

    gpus: list[dict[str, Any]] = []
    sp = _run(["system_profiler", "SPDisplaysDataType"], timeout=10.0)
    if sp:
        # Best-effort line scrape; just record GPU model name(s).
        current: dict[str, Any] | None = None
        for raw_line in sp.splitlines():
            line = raw_line.rstrip()
            if not line:
                continue
            stripped = line.strip()
            indent = len(line) - len(stripped)
            if indent == 4 and stripped.endswith(":") and "Display" not in stripped:
                if current:
                    gpus.append(current)
                current = {"model": stripped[:-1], "vram_mb": None}
            elif current is not None and stripped.startswith("VRAM"):
                # "VRAM (Total): 8 GB" or "VRAM (Dynamic, Max): ..."
                _, _, value = stripped.partition(":")
                value = value.strip()
                if value.endswith("GB"):
                    try:
                        current["vram_mb"] = int(float(value.split()[0]) * 1024)
                    except ValueError:
                        pass
                elif value.endswith("MB"):
                    try:
                        current["vram_mb"] = int(float(value.split()[0]))
                    except ValueError:
                        pass
        if current:
            gpus.append(current)

    return {
        "cpu_model": cpu_model,
        "cpu_count": cpu_count,
        "ram_mb": ram_mb,
        "chip": chip_raw,
        "hardware_model": hardware_model,
        "hardware_model_name": sp_fields.get("hardware_model_name"),
        "hardware_model_identifier": sp_fields.get("hardware_model_identifier"),
        "gpus": gpus,
    }


def _collect_linux() -> dict[str, Any]:
    cpu_model: str | None = None
    cpu_count: int | None = None
    lscpu = _run(["lscpu"])
    if lscpu:
        for line in lscpu.splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if key == "Model name" and not cpu_model:
                cpu_model = value
            elif key == "CPU(s)" and value.isdigit():
                cpu_count = int(value)

    ram_mb: int | None = None
    free = _run(["free", "-m"])
    if free:
        for line in free.splitlines():
            if line.lower().startswith("mem:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    ram_mb = int(parts[1])
                break

    os_release = _read_file(Path("/etc/os-release"))
    distro = _parse_os_release(os_release).get("PRETTY_NAME") if os_release else None

    gpus: list[dict[str, Any]] = []
    smi = _run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]
    )
    if smi:
        for line in smi.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                vram_mb: int | None
                try:
                    vram_mb = int(parts[1])
                except ValueError:
                    vram_mb = None
                gpus.append(
                    {
                        "model": parts[0],
                        "vram_mb": vram_mb,
                        "driver_version": parts[2] if len(parts) >= 3 else None,
                    }
                )

    return {
        "cpu_model": cpu_model,
        "cpu_count": cpu_count,
        "ram_mb": ram_mb,
        "distro": distro,
        "gpus": gpus,
    }


def collect_hardware() -> dict[str, Any]:
    """Return host metadata for ``hardware.json``.

    Best-effort: every shell call is allowed to fail; missing fields are ``None``.
    """
    system = platform.system().lower()
    base: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "platform": "darwin"
        if system == "darwin"
        else "linux"
        if system == "linux"
        else "other",
        "os": platform.platform(),
        "kernel": platform.release() or None,
        "cpu_model": None,
        "cpu_count": None,
        "ram_mb": None,
        "gpus": [],
    }

    try:
        if base["platform"] == "darwin":
            base.update(_collect_macos())
        elif base["platform"] == "linux":
            base.update(_collect_linux())
    except Exception as exc:  # pragma: no cover - defensive: never block a run
        base["collector_error"] = repr(exc)

    return base


def sample_resources() -> dict[str, Any]:
    """Sample peak runtime resources.

    Phase 1 cannot observe the inference process directly (it is typically a
    separate daemon such as Ollama).  GPU memory is sampled via ``nvidia-smi``
    when available; everything else degrades to ``None`` per the
    architecture's "best-effort" rule.
    """
    sample: dict[str, Any] = {"memory_mb": None, "gpu_memory_mb": None}

    smi = _run(
        [
            "nvidia-smi",
            "--query-gpu=memory.used",
            "--format=csv,noheader,nounits",
        ]
    )
    if smi:
        try:
            values = [int(line.strip()) for line in smi.strip().splitlines() if line.strip()]
            if values:
                sample["gpu_memory_mb"] = max(values)
        except ValueError:
            pass

    return sample
