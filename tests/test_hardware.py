"""Tests for benchpack.hardware (best-effort collector)."""

from __future__ import annotations

import benchpack.hardware as hardware
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


def test_parse_system_profiler_hardware_extracts_apple_identity() -> None:
    parsed = hardware._parse_system_profiler_hardware(
        """
Hardware:

    Hardware Overview:

      Model Name: Mac Studio
      Model Identifier: Mac16,9
      Chip: Apple M4 Max
      Total Number of Cores: 16 (12 performance and 4 efficiency)
      Memory: 64 GB
"""
    )

    assert parsed == {
        "hardware_model_name": "Mac Studio",
        "hardware_model_identifier": "Mac16,9",
        "chip": "Apple M4 Max",
        "cpu_count": 16,
        "ram_mb": 65536,
    }


def test_collect_macos_records_model_identity_and_sp_fallbacks(monkeypatch) -> None:
    def fake_run(cmd, timeout=5.0):
        if cmd == ["sysctl", "-n", "machdep.cpu.brand_string"]:
            return "Apple processor\n"
        if cmd == ["sysctl", "-n", "hw.ncpu"]:
            return "\n"
        if cmd == ["sysctl", "-n", "hw.memsize"]:
            return "\n"
        if cmd == ["sysctl", "-n", "hw.model"]:
            return "Mac16,9\n"
        if cmd == ["system_profiler", "SPHardwareDataType"]:
            return """
Hardware:

    Hardware Overview:

      Model Name: Mac Studio
      Model Identifier: Mac16,9
      Chip: Apple M4 Max
      Total Number of Cores: 16 (12 performance and 4 efficiency)
      Memory: 64 GB
"""
        if cmd == ["system_profiler", "SPDisplaysDataType"]:
            return """
Graphics/Displays:

    Apple M4 Max:

      Chipset Model: Apple M4 Max
      Type: GPU
      Bus: Built-In
"""
        raise AssertionError(f"unexpected command: {cmd}")

    monkeypatch.setattr(hardware, "_run", fake_run)

    hw = hardware._collect_macos()

    assert hw["cpu_model"] == "Apple M4 Max"
    assert hw["chip"] == "Apple M4 Max"
    assert hw["cpu_count"] == 16
    assert hw["ram_mb"] == 65536
    assert hw["hardware_model"] == "Mac16,9"
    assert hw["hardware_model_name"] == "Mac Studio"
    assert hw["hardware_model_identifier"] == "Mac16,9"
    assert hw["gpus"] == [{"model": "Apple M4 Max", "vram_mb": None}]


def test_sample_resources_returns_required_keys() -> None:
    sample = sample_resources()
    assert "memory_mb" in sample
    assert "gpu_memory_mb" in sample


def test_malformed_memory_is_unavailable() -> None:
    for value in ('nan GB', 'inf MB', '-1 GB', '1e308 TB', 'bad GB', ''):
        assert hardware._parse_memory_mb(value) is None
    assert hardware._parse_memory_mb('1.5 GB') == 1536


def test_empty_cores_preserves_partial_metadata() -> None:
    parsed = hardware._parse_system_profiler_hardware(
        'Chip: Apple M4\nTotal Number of Cores: \nMemory: nan GB'
    )
    assert parsed['chip'] == 'Apple M4'
    assert parsed['cpu_count'] is None
    assert parsed['ram_mb'] is None


def test_decoding_failures_are_unavailable(monkeypatch, tmp_path) -> None:
    def invalid_encoding(*args, **kwargs):
        raise UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid')

    monkeypatch.setattr(hardware.subprocess, 'run', invalid_encoding)
    assert hardware._run(['fake']) is None
    evidence = tmp_path / 'os-release'
    evidence.write_bytes(b'\xff')
    monkeypatch.setattr(type(evidence), 'read_text', invalid_encoding)
    assert hardware._read_file(evidence) is None


def test_collection_preserves_identity_with_malformed_evidence(monkeypatch) -> None:
    monkeypatch.setattr(hardware.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(hardware, '_sysctl', lambda key: None)

    def fake_run(cmd, timeout=5.0):
        if cmd[-1] == 'SPHardwareDataType':
            return 'Chip: Apple M4\nTotal Number of Cores: \nMemory: inf MB'
        return '    Apple GPU:\n      VRAM (Total): inf MB'

    monkeypatch.setattr(hardware, '_run', fake_run)
    hw = collect_hardware()
    assert hw['cpu_model'] == 'Apple M4'
    assert hw['cpu_count'] is None
    assert hw['ram_mb'] is None
    assert hw['gpus'] == [{'model': 'Apple GPU', 'vram_mb': None}]
    assert 'collector_error' not in hw


def test_malformed_integer_evidence_preserves_linux_metadata(monkeypatch):
    monkeypatch.setattr(hardware.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(hardware, '_read_file', lambda path: 'PRETTY_NAME="Test Linux"')
    for malformed in ('²', '9' * 5000, '-1', 'nan'):
        def fake_run(cmd, timeout=5.0):
            if cmd == ['lscpu']:
                return f'Model name: Test CPU\nCPU(s): {malformed}'
            if cmd == ['free', '-m']:
                return f'Mem: {malformed}'
            return 'Test GPU, -1, driver'
        monkeypatch.setattr(hardware, '_run', fake_run)
        hw = collect_hardware()
        assert hw['cpu_model'] == 'Test CPU'
        assert hw['cpu_count'] is None
        assert hw['ram_mb'] is None
        assert hw['distro'] == 'Test Linux'
        assert hw['gpus'][0]['vram_mb'] is None
        assert 'collector_error' not in hw
    assert hardware._parse_nonnegative_int('16') == 16
    assert hardware._parse_memory_mb('1 TB') == 1048576
