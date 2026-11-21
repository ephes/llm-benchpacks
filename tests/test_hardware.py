"""Tests for benchpack.hardware (best-effort collector)."""

from __future__ import annotations

import os
from unittest.mock import Mock

import pytest

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

    monkeypatch.setattr(subprocess, "Popen", boom)
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


def test_decoding_failures_are_unavailable(tmp_path) -> None:
    import sys
    assert hardware._run([sys.executable, '-c', "import os; os.write(1, b'\\xff')"]) is None
    evidence = tmp_path / 'os-release'
    evidence.write_bytes(b'\xff')
    assert hardware._read_file(evidence) is None


def test_collection_preserves_identity_with_malformed_evidence(monkeypatch) -> None:
    monkeypatch.setattr(hardware.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(hardware, '_sysctl', lambda key, deadline=None: None)

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


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ("regular", "Test Linux"),
        ("symlink", "Test Linux"),
        ("limit", "Test Linux"),
        ("oversized", None),
        ("directory", None),
        ("missing", None),
    ],
)
def test_linux_release_file_preserves_other_hardware(monkeypatch, tmp_path, evidence, expected):
    release = tmp_path / "os-release"
    payload = b'PRETTY_NAME="Test Linux"\nID=test\n'
    if evidence == "symlink":
        target = tmp_path / "vendor-release"
        target.write_bytes(payload)
        release.symlink_to(target.name)
    elif evidence == "directory":
        release.mkdir()
    elif evidence != "missing":
        if evidence in {"limit", "oversized"}:
            size = 64 * 1024 + (evidence == "oversized")
            payload += b"#" * (size - len(payload))
        release.write_bytes(payload)

    read_file = hardware._read_file
    monkeypatch.setattr(hardware, "_read_file", lambda path: read_file(release))
    monkeypatch.setattr(hardware.platform, "system", lambda: "Linux")
    outputs = {
        "lscpu": "Model name: Test CPU\nCPU(s): 8",
        "free": "Mem: 4096",
        "nvidia-smi": "Test GPU, 1024, driver",
    }
    monkeypatch.setattr(hardware, "_run", lambda cmd, timeout: outputs[cmd[0]])

    hw = collect_hardware()
    assert hw["distro"] == expected
    assert hw["cpu_model"] == "Test CPU"
    assert hw["cpu_count"] == 8
    assert hw["ram_mb"] == 4096
    assert hw["gpus"] == [{"model": "Test GPU", "vram_mb": 1024, "driver_version": "driver"}]
    assert "collector_error" not in hw


def test_linux_probe_uses_c_locale_without_changing_parent(monkeypatch, tmp_path):
    probe = tmp_path / "lscpu"
    probe.write_text(
        '#!/bin/sh\n'
        'if [ "$LC_ALL" = C ]; then\n'
        '    printf "Model name: Test CPU\\nCPU(s): 8\\n"\n'
        'else\n'
        '    printf "Modellname: Test CPU\\nProzessoren: 8\\n"\n'
        'fi\n',
        encoding="utf-8",
    )
    probe.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LC_ALL", "de_DE.UTF-8")
    monkeypatch.setattr(hardware.platform, "system", lambda: "Linux")

    hw = collect_hardware()

    assert hw["cpu_model"] == "Test CPU"
    assert hw["cpu_count"] == 8
    assert os.environ["LC_ALL"] == "de_DE.UTF-8"


def test_probe_output_budget_and_recovery():
    import sys
    # Both streams count, including discarded stderr. Partial stdout is refused.
    for stream in ('stdout', 'stderr'):
        source = f"import sys; sys.{stream}.write('x' * (64 * 1024 + 1))"
        assert hardware._run([sys.executable, '-c', source]) is None
    assert hardware._run([sys.executable, '-c', "print('ready')"]) == 'ready\n'


def test_collector_uses_one_deadline(monkeypatch):
    import time
    monkeypatch.setattr(hardware, 'COLLECTOR_TIMEOUT_S', 0.05, raising=False)
    monkeypatch.setattr(hardware.platform, 'system', lambda: 'Darwin')
    calls = []

    def stalled(cmd, timeout=5.0):
        calls.append(timeout)
        time.sleep(0.06)
        return None

    monkeypatch.setattr(hardware, '_run', stalled)
    started = time.monotonic()
    result = collect_hardware()
    assert time.monotonic() - started < 0.2
    assert len(calls) == 1
    assert 0 < calls[0] <= 0.05
    assert result['cpu_model'] is None


def test_probe_retires_pipe_holding_descendants(tmp_path):
    import sys
    import time
    import pytest
    import os
    if os.name != 'posix':
        pytest.skip('POSIX process-group ownership')
    for leader_exits in (True, False):
        marker = tmp_path / str(leader_exits)
        child = f'import time; from pathlib import Path; time.sleep(0.6); Path({str(marker)!r}).touch()'
        source = (
            'import subprocess, sys, time; '
            f'subprocess.Popen([sys.executable, "-c", {child!r}]); '
            + ('print("complete", flush=True)' if leader_exits else 'time.sleep(2)')
        )
        # The success case only needs the leader to start, spawn and print
        # before its descendant's 0.6 s sleep ends; give slow runners headroom.
        timeout = 1.0 if leader_exits else 0.15
        started = time.monotonic()
        result = hardware._run([sys.executable, '-c', source], timeout=timeout)
        assert time.monotonic() - started < timeout + 0.35
        assert result == ('complete\n' if leader_exits else None)
        time.sleep(0.7)
        assert not marker.exists(), 'owned descendant survived collection'


def test_probe_unkillable_leader_stays_unavailable(monkeypatch, tmp_path):
    import os
    import signal
    import sys
    import time
    import pytest

    if os.name != 'posix':
        pytest.skip('POSIX signal cleanup')
    pid_file = tmp_path / 'pid'
    source = (
        'import os, time; from pathlib import Path; '
        f'Path({str(pid_file)!r}).write_text(str(os.getpid())); time.sleep(3)'
    )
    for failure in (None, PermissionError):
        def stuck(process, failure=failure):
            # Simulate a leader that ignores SIGKILL (e.g. uninterruptible sleep).
            if failure is not None:
                raise failure('synthetic EPERM')

        monkeypatch.setattr(hardware, '_retire_probe', stuck)
        started = time.monotonic()
        try:
            assert hardware._run([sys.executable, '-c', source], timeout=0.3) is None
            assert time.monotonic() - started < 1.0
        finally:
            for _ in range(50):
                if pid_file.exists() and pid_file.read_text():
                    break
                time.sleep(0.02)
            if pid_file.exists() and pid_file.read_text():
                try:
                    os.kill(int(pid_file.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            pid_file.unlink(missing_ok=True)


def test_probe_combined_budget_boundary():
    import sys
    source = "import os; os.write(1, b'x' * 32768); os.write(2, b'\\xff' * 32768)"
    assert hardware._run([sys.executable, '-c', source]) == 'x' * 32768
    assert hardware._run([sys.executable, '-c', source + "; os.write(2, b'z')"]) is None


def test_probe_timeout_after_pipes_close():
    import sys
    import time
    started = time.monotonic()
    assert hardware._run([sys.executable, '-c',
                          'import os,time; os.close(1); os.close(2); time.sleep(5)'],
                         timeout=0.1) is None
    assert time.monotonic() - started < 0.5


@pytest.mark.parametrize("failed_handle", ["selector", "stdout", "stderr"])
@pytest.mark.parametrize(("returncode", "expected"), [(0, ""), (1, None)])
def test_probe_close_failure_preserves_result_and_reaps(
    monkeypatch, failed_handle, returncode, expected
):
    selector = Mock()
    selector.get_map.return_value = {}
    process = Mock(returncode=returncode)
    process.poll.return_value = returncode
    handles = {"selector": selector, "stdout": process.stdout, "stderr": process.stderr}
    handles[failed_handle].close.side_effect = OSError("synthetic close failure")
    monkeypatch.setattr(hardware.selectors, "DefaultSelector", lambda: selector)
    monkeypatch.setattr(hardware.subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr(hardware.os, "set_blocking", Mock())
    retire = Mock()
    monkeypatch.setattr(hardware, "_retire_probe", retire)

    assert hardware._run(["probe"]) == expected
    retire.assert_called_once_with(process)
    for handle in handles.values():
        handle.close.assert_called_once_with()
    process.wait.assert_called_once_with(timeout=0.25)


def test_probe_selector_failure_retires_process(monkeypatch):
    import sys
    import subprocess
    processes = []
    popen = subprocess.Popen

    def launch(*args, **kwargs):
        process = popen(*args, **kwargs)
        processes.append(process)
        return process

    def unavailable():
        raise OSError('synthetic selector failure')

    monkeypatch.setattr(hardware.subprocess, 'Popen', launch)
    monkeypatch.setattr(hardware.selectors, 'DefaultSelector', unavailable)
    try:
        assert hardware._run([sys.executable, '-c', 'import time; time.sleep(5)']) is None
        assert processes[0].poll() is not None
        assert processes[0].stdout.closed and processes[0].stderr.closed
    finally:
        for process in processes:
            process.kill()
            process.wait(timeout=1)
            process.stdout.close()
            process.stderr.close()
