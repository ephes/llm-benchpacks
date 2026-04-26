"""Tests for benchpack.hardware (best-effort collector)."""

from __future__ import annotations

from benchpack.hardware import collect_hardware, sample_resources


REQUIRED_HARDWARE_KEYS = {
    "hostname",
    "os",
    "kernel",
    "cpu_model",
    "cpu_count",
    "ram_mb",
    "gpus",
    "platform",
}


def test_collect_hardware_returns_expected_shape() -> None:
    hw = collect_hardware()
    for key in REQUIRED_HARDWARE_KEYS:
        assert key in hw, f"hardware.json missing field: {key}"
    assert hw["platform"] in {"darwin", "linux", "other"}
    # hostname is one of the few fields stdlib can always supply
    assert isinstance(hw["hostname"], str) and hw["hostname"]
    # gpus is always a list (may be empty)
    assert isinstance(hw["gpus"], list)


def test_collect_hardware_never_raises_when_tools_missing(monkeypatch) -> None:
    import subprocess

    def boom(*args, **kwargs):
        raise FileNotFoundError("tool unavailable")

    monkeypatch.setattr(subprocess, "run", boom)
    hw = collect_hardware()
    # All shell-derived values should degrade to None / empty rather than raise
    assert hw["hostname"]  # still works via socket.gethostname
    assert hw["cpu_model"] is None
    assert hw["ram_mb"] is None
    assert hw["gpus"] == []


def test_sample_resources_returns_required_keys() -> None:
    sample = sample_resources()
    assert "memory_mb" in sample
    assert "gpu_memory_mb" in sample
