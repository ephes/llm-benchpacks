"""Tests for deterministic repo-task task log helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchpack.packs import Case, Fixture, Pack, Scoring
from benchpack.patches import capture_workspace_patch
from benchpack.tasks import (
    AgentSessionHarnessRequest,
    AgentSessionHarnessResult,
    TaskArtifactPaths,
    TaskError,
    TaskExecutionRequest,
    apply_unified_diff_to_workspace,
    extract_fenced_patch,
    run_model_patch_task,
    run_repo_task_executor,
    task_artifact_paths,
    task_record,
    write_noop_task_logs,
)
from benchpack.verifiers import run_repo_task_verifier
from benchpack.workspaces import PreparedWorkspace


def make_case() -> Case:
    return Case(
        id="edit-repo",
        kind="repo-task",
        prompt="Change the repository.",
        scoring=None,
        raw={},
    )


def make_repo_fixture(source: Path) -> Fixture:
    return Fixture(
        id="repo",
        kind="repo",
        path=source,
        description="",
        raw={"id": "repo", "kind": "repo", "path": "fixtures/repo"},
    )


def test_task_artifact_paths_use_run_relative_layout(tmp_path: Path) -> None:
    paths = task_artifact_paths(tmp_path / "run", make_case(), 1)

    assert paths.stdout == (
        tmp_path / "run" / "task" / "edit-repo" / "rep-001.stdout.log"
    )
    assert paths.stderr == (
        tmp_path / "run" / "task" / "edit-repo" / "rep-001.stderr.log"
    )


@pytest.mark.parametrize("repetition", [0, -1, True, "1"])
def test_task_artifact_paths_reject_invalid_repetition(
    tmp_path: Path,
    repetition: object,
) -> None:
    with pytest.raises(ValueError, match="repetition"):
        task_artifact_paths(
            tmp_path / "run",
            make_case(),
            repetition,  # type: ignore[arg-type]
        )


def test_task_record_uses_run_relative_posix_paths(tmp_path: Path) -> None:
    out = tmp_path / "run"
    paths = TaskArtifactPaths(
        stdout=out / "task" / "edit-repo" / "rep-001.stdout.log",
        stderr=out / "task" / "edit-repo" / "rep-001.stderr.log",
    )

    assert task_record(paths, out) == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }


def test_task_record_rejects_paths_outside_output_dir(tmp_path: Path) -> None:
    paths = TaskArtifactPaths(
        stdout=tmp_path / "outside" / "rep-001.stdout.log",
        stderr=tmp_path / "run" / "task" / "edit-repo" / "rep-001.stderr.log",
    )

    with pytest.raises(TaskError, match="not under run output directory"):
        task_record(paths, tmp_path / "run")


def test_write_noop_task_logs_creates_empty_logs_and_record(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"

    record = write_noop_task_logs(out, make_case(), 1)

    assert record == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert (out / record["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["stderr_path"]).read_text(encoding="utf-8") == ""


def test_extract_fenced_patch_returns_first_diff_block() -> None:
    output = """Explanation.

```python
print("ignored")
```

```diff
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-old
+new
```

```patch
ignored
```
"""

    assert extract_fenced_patch(output) == (
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )


def test_extract_fenced_patch_returns_first_patch_block() -> None:
    output = """Text before.

```patch
--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-a
+b
```
"""

    assert extract_fenced_patch(output).startswith("--- a/file.txt\n")  # type: ignore[union-attr]


def test_extract_fenced_patch_ignores_non_matching_fences() -> None:
    output = """```python
not a patch
```

```diff extra
not a patch
```
"""

    assert extract_fenced_patch(output) is None


def test_apply_unified_diff_to_workspace_mutates_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("old\nshared\n", encoding="utf-8")
    diff = (
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1,2 +1,2 @@\n"
        "-old\n"
        "+new\n"
        " shared\n"
    )

    applied, stdout, stderr = apply_unified_diff_to_workspace(diff, workspace)

    assert applied is True
    assert stdout == "Applied fenced model patch to workspace.\n"
    assert stderr == ""
    assert (workspace / "README.md").read_text(encoding="utf-8") == "new\nshared\n"


def test_apply_unified_diff_to_workspace_handles_git_header_path_with_spaces(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "file with spaces.txt").write_text("old\n", encoding="utf-8")
    diff = (
        "diff --git a/file with spaces.txt b/file with spaces.txt\n"
        "--- a/file with spaces.txt\n"
        "+++ b/file with spaces.txt\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    applied, stdout, stderr = apply_unified_diff_to_workspace(diff, workspace)

    assert applied is True
    assert stdout == "Applied fenced model patch to workspace.\n"
    assert stderr == ""
    assert (workspace / "file with spaces.txt").read_text(encoding="utf-8") == "new\n"


def test_apply_unified_diff_to_workspace_adds_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    diff = (
        "--- /dev/null\n"
        "+++ b/new.txt\n"
        "@@ -0,0 +1 @@\n"
        "+new\n"
    )

    applied, stdout, stderr = apply_unified_diff_to_workspace(diff, workspace)

    assert applied is True
    assert stdout == "Applied fenced model patch to workspace.\n"
    assert stderr == ""
    assert (workspace / "new.txt").read_text(encoding="utf-8") == "new\n"


def test_apply_unified_diff_to_workspace_deletes_file(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    deleted = workspace / "deleted.txt"
    deleted.write_text("delete me\n", encoding="utf-8")
    diff = (
        "--- a/deleted.txt\n"
        "+++ /dev/null\n"
        "@@ -1 +0,0 @@\n"
        "-delete me\n"
    )

    applied, stdout, stderr = apply_unified_diff_to_workspace(diff, workspace)

    assert applied is True
    assert stdout == "Applied fenced model patch to workspace.\n"
    assert stderr == ""
    assert not deleted.exists()


def test_apply_unified_diff_to_workspace_renames_file_from_git_header(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    old = workspace / "old.txt"
    new = workspace / "new.txt"
    old.write_text("same\n", encoding="utf-8")
    diff = (
        "diff --git a/old.txt b/new.txt\n"
        "similarity index 100%\n"
        "rename from old.txt\n"
        "rename to new.txt\n"
    )

    applied, stdout, stderr = apply_unified_diff_to_workspace(diff, workspace)

    assert applied is True
    assert stdout == "Applied fenced model patch to workspace.\n"
    assert stderr == ""
    assert not old.exists()
    assert new.read_text(encoding="utf-8") == "same\n"


def test_run_model_patch_task_no_matching_block_logs_stderr_and_keeps_workspace(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("old\n", encoding="utf-8")

    record = run_model_patch_task(
        out,
        make_case(),
        1,
        workspace,
        "No patch here.\n```python\nprint('ignored')\n```\n",
    )

    assert record == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert (workspace / "README.md").read_text(encoding="utf-8") == "old\n"
    assert (out / record["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["stderr_path"]).read_text(encoding="utf-8") == (
        "No fenced diff or patch block found in model output; "
        "workspace left unchanged.\n"
    )


def test_run_model_patch_task_invalid_patch_logs_stderr_and_keeps_row_flow(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("old\n", encoding="utf-8")

    record = run_model_patch_task(
        out,
        make_case(),
        1,
        workspace,
        "```diff\n--- a/README.md\n+++ b/README.md\nnot a hunk\n```\n",
    )

    assert (workspace / "README.md").read_text(encoding="utf-8") == "old\n"
    assert (out / record["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["stderr_path"]).read_text(encoding="utf-8") == (
        "Patch rejected: unified diff could not be applied cleanly; "
        "workspace left unchanged.\n"
    )


def test_run_repo_task_executor_runs_fenced_model_output_patch_executor(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("old\n", encoding="utf-8")

    record = run_repo_task_executor(
        TaskExecutionRequest(
            output_dir=out,
            case=make_case(),
            repetition=1,
            workspace=workspace,
            model_output_text=(
                "```diff\n"
                "--- a/README.md\n"
                "+++ b/README.md\n"
                "@@ -1 +1 @@\n"
                "-old\n"
                "+new\n"
                "```\n"
            ),
        )
    )

    assert record == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert (workspace / "README.md").read_text(encoding="utf-8") == "new\n"
    assert (out / record["stdout_path"]).read_text(encoding="utf-8") == (
        "Applied fenced model patch to workspace.\n"
    )
    assert (out / record["stderr_path"]).read_text(encoding="utf-8") == ""


def test_run_repo_task_executor_internal_harness_mutation_reaches_patch_and_verifier(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    pack_dir = tmp_path / "pack"
    source = pack_dir / "fixtures" / "repo"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    source.mkdir(parents=True)
    workspace.mkdir(parents=True)
    (source / "README.md").write_text("source repo\n", encoding="utf-8")
    (workspace / "README.md").write_text("source repo\n", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    case = Case(
        id="edit-repo",
        kind="repo-task",
        prompt="Change the repository.",
        scoring=Scoring(mode="verify-script", script="verify/check.py"),
        raw={},
        fixture_refs=["repo"],
    )
    seen: dict[str, Path] = {}

    def harness(request: AgentSessionHarnessRequest) -> AgentSessionHarnessResult:
        seen["workspace"] = request.workspace
        seen["stdout"] = request.task_paths.stdout
        seen["stderr"] = request.task_paths.stderr
        assert request.task_paths == task_artifact_paths(out, case, 1)
        assert request.read_workspace_text("README.md") == "source repo\n"
        request.write_workspace_text("README.md", "harness repo\n")
        request.write_workspace_text("nested/created.txt", "created\n")
        with pytest.raises(TaskError, match="unsafe harness workspace path"):
            request.read_workspace_text("../outside.txt")
        with pytest.raises(TaskError, match="unsafe harness workspace path"):
            request.write_workspace_text("../outside.txt", "bad\n")
        return AgentSessionHarnessResult(
            stdout="harness stdout\n",
            stderr="harness stderr\n",
        )

    record = run_repo_task_executor(
        TaskExecutionRequest(
            output_dir=out,
            case=case,
            repetition=1,
            workspace=workspace,
            model_output_text="adapter output remains available",
            agent_session_harness=harness,
        )
    )

    assert record == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert seen == {
        "workspace": workspace,
        "stdout": out / "task" / "edit-repo" / "rep-001.stdout.log",
        "stderr": out / "task" / "edit-repo" / "rep-001.stderr.log",
    }
    assert (source / "README.md").read_text(encoding="utf-8") == "source repo\n"
    assert outside.read_text(encoding="utf-8") == "outside\n"
    assert (workspace / "README.md").read_text(encoding="utf-8") == "harness repo\n"
    assert (workspace / "nested" / "created.txt").read_text(
        encoding="utf-8"
    ) == "created\n"
    assert (out / record["stdout_path"]).read_text(encoding="utf-8") == (
        "harness stdout\n"
    )
    assert (out / record["stderr_path"]).read_text(encoding="utf-8") == (
        "harness stderr\n"
    )

    fixture = make_repo_fixture(source)
    prepared = PreparedWorkspace(source_fixture=fixture, path=workspace)
    patch_metadata = capture_workspace_patch(prepared, out, case, 1)
    assert patch_metadata == {"path": "patch/edit-repo/rep-001.diff"}
    assert (out / patch_metadata["path"]).read_text(encoding="utf-8") == (
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-source repo\n"
        "+harness repo\n"
        "--- /dev/null\n"
        "+++ b/nested/created.txt\n"
        "@@ -0,0 +1 @@\n"
        "+created\n"
    )

    script = pack_dir / "verify" / "check.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--workspace")
parser.add_argument("--case")
parser.add_argument("--pack-id")
parser.add_argument("--pack-version")
parser.add_argument("--source-fixture-id")
parser.add_argument("--patch")
parser.add_argument("--output")
args = parser.parse_args()
content = Path(args.workspace, "README.md").read_text(encoding="utf-8")
if content != "harness repo\\n":
    raise SystemExit(2)
with open(args.output, "w", encoding="utf-8") as fh:
    json.dump({"content": content, "patch_exists": Path(args.patch).exists()}, fh)
""",
        encoding="utf-8",
    )
    pack = Pack(
        id="repo-pack",
        version="0.1.0",
        description="",
        defaults={},
        cases=[case],
        scoring=None,
        path=pack_dir,
        fixtures=[fixture],
    )

    verifier_result = run_repo_task_verifier(
        pack=pack,
        case=case,
        scoring=case.scoring,  # type: ignore[arg-type]
        prepared_workspace=prepared,
        patch_path=out / patch_metadata["path"],
        output_dir=out,
        repetition=1,
        timeout_s=5.0,
    )

    assert verifier_result.repo_task == {"status": "passed", "verify_exit_code": 0}
    assert verifier_result.scoring == {"mode": "verify-script", "passed": True}
    assert json.loads((out / verifier_result.verify["path"]).read_text()) == {
        "content": "harness repo\n",
        "exit_code": 0,
        "passed": True,
        "patch_exists": True,
    }


def test_run_repo_task_executor_internal_harness_realistic_fake_agent_sequence(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    pack_dir = tmp_path / "pack"
    source = pack_dir / "fixtures" / "repo"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    source.mkdir(parents=True)
    workspace.mkdir(parents=True)
    (source / "README.md").write_text("# Source Repository\n", encoding="utf-8")
    (source / "pyproject.toml").write_text(
        "[project]\nname = \"source-repo\"\n",
        encoding="utf-8",
    )
    (workspace / "README.md").write_text("# Source Repository\n", encoding="utf-8")
    (workspace / "pyproject.toml").write_text(
        "[project]\nname = \"source-repo\"\n",
        encoding="utf-8",
    )
    case = Case(
        id="edit-repo",
        kind="repo-task",
        prompt="Make the repository runnable.",
        scoring=Scoring(mode="verify-script", script="verify/check.py"),
        raw={},
        fixture_refs=["repo"],
    )

    stdout = (
        "fake-agent: rewrote README.md\n"
        "fake-agent: created src/app.py\n"
        "fake-agent: created src/utils/formatting.py\n"
        "fake-agent: created tests/test_app.py\n"
        "fake-agent: created docs/notes.md\n"
    )
    stderr = "fake-agent: deterministic trace\n"

    def harness(request: AgentSessionHarnessRequest) -> AgentSessionHarnessResult:
        assert request.output_dir == out
        assert request.case == case
        assert request.repetition == 1
        assert request.workspace == workspace
        assert request.model_output_text == "adapter output for fake agent"
        assert request.workspace_path("README.md") == workspace / "README.md"
        assert request.read_workspace_text("README.md") == "# Source Repository\n"
        assert request.read_workspace_text("pyproject.toml") == (
            "[project]\nname = \"source-repo\"\n"
        )
        request.write_workspace_text("README.md", "# Draft Repository\n")
        request.write_workspace_text("README.md", "# Edited Repository\n")
        request.write_workspace_text(
            "src/app.py",
            (
                "from utils.formatting import format_greeting\n"
                "\n"
                "\n"
                "def run(name: str) -> str:\n"
                "    return format_greeting(name)\n"
            ),
        )
        request.write_workspace_text(
            "src/utils/formatting.py",
            (
                "def format_greeting(name: str) -> str:\n"
                "    return f\"Hello, {name}!\"\n"
            ),
        )
        request.write_workspace_text(
            "tests/test_app.py",
            (
                "from src.app import run\n"
                "\n"
                "\n"
                "def test_run_formats_greeting():\n"
                "    assert run(\"Ada\") == \"Hello, Ada!\"\n"
            ),
        )
        request.write_workspace_text(
            "docs/notes.md",
            "# Notes\n\nFake agent created sibling docs and source trees.\n",
        )
        return AgentSessionHarnessResult(stdout=stdout, stderr=stderr)

    record = run_repo_task_executor(
        TaskExecutionRequest(
            output_dir=out,
            case=case,
            repetition=1,
            workspace=workspace,
            model_output_text="adapter output for fake agent",
            agent_session_harness=harness,
        )
    )

    assert record == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert (out / record["stdout_path"]).read_text(encoding="utf-8") == stdout
    assert (out / record["stderr_path"]).read_text(encoding="utf-8") == stderr

    assert (source / "README.md").read_text(encoding="utf-8") == (
        "# Source Repository\n"
    )
    assert (source / "pyproject.toml").read_text(encoding="utf-8") == (
        "[project]\nname = \"source-repo\"\n"
    )
    for relative_path in [
        "src/app.py",
        "src/utils/formatting.py",
        "tests/test_app.py",
        "docs/notes.md",
    ]:
        assert not (source / relative_path).exists()

    assert (workspace / "README.md").read_text(encoding="utf-8") == (
        "# Edited Repository\n"
    )
    assert (workspace / "src" / "app.py").read_text(encoding="utf-8") == (
        "from utils.formatting import format_greeting\n"
        "\n"
        "\n"
        "def run(name: str) -> str:\n"
        "    return format_greeting(name)\n"
    )
    assert (workspace / "src" / "utils" / "formatting.py").read_text(
        encoding="utf-8"
    ) == (
        "def format_greeting(name: str) -> str:\n"
        "    return f\"Hello, {name}!\"\n"
    )
    assert (workspace / "tests" / "test_app.py").read_text(encoding="utf-8") == (
        "from src.app import run\n"
        "\n"
        "\n"
        "def test_run_formats_greeting():\n"
        "    assert run(\"Ada\") == \"Hello, Ada!\"\n"
    )
    assert (workspace / "docs" / "notes.md").read_text(encoding="utf-8") == (
        "# Notes\n\nFake agent created sibling docs and source trees.\n"
    )

    fixture = make_repo_fixture(source)
    prepared = PreparedWorkspace(source_fixture=fixture, path=workspace)
    patch_metadata = capture_workspace_patch(prepared, out, case, 1)
    assert patch_metadata == {"path": "patch/edit-repo/rep-001.diff"}
    patch_text = (out / patch_metadata["path"]).read_text(encoding="utf-8")
    assert "pyproject.toml" not in patch_text
    for expected in [
        "--- a/README.md\n+++ b/README.md\n",
        "+++ b/docs/notes.md\n",
        "+++ b/src/app.py\n",
        "+++ b/src/utils/formatting.py\n",
        "+++ b/tests/test_app.py\n",
        "-# Source Repository\n",
        "+# Edited Repository\n",
        "+from utils.formatting import format_greeting\n",
        "+def format_greeting(name: str) -> str:\n",
        "+def test_run_formats_greeting():\n",
        "+Fake agent created sibling docs and source trees.\n",
    ]:
        assert expected in patch_text

    script = pack_dir / "verify" / "check.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        """
import argparse
import json
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument("--workspace")
parser.add_argument("--case")
parser.add_argument("--pack-id")
parser.add_argument("--pack-version")
parser.add_argument("--source-fixture-id")
parser.add_argument("--patch")
parser.add_argument("--output")
args = parser.parse_args()
workspace = Path(args.workspace)
expected = {
    "README.md": "# Edited Repository\\n",
    "src/app.py": (
        "from utils.formatting import format_greeting\\n"
        "\\n"
        "\\n"
        "def run(name: str) -> str:\\n"
        "    return format_greeting(name)\\n"
    ),
    "src/utils/formatting.py": (
        "def format_greeting(name: str) -> str:\\n"
        "    return f\\"Hello, {name}!\\"\\n"
    ),
    "tests/test_app.py": (
        "from src.app import run\\n"
        "\\n"
        "\\n"
        "def test_run_formats_greeting():\\n"
        "    assert run(\\"Ada\\") == \\"Hello, Ada!\\"\\n"
    ),
    "docs/notes.md": "# Notes\\n\\nFake agent created sibling docs and source trees.\\n",
}
for relative_path, expected_content in expected.items():
    if (workspace / relative_path).read_text(encoding="utf-8") != expected_content:
        raise SystemExit(2)
patch_path = Path(args.patch)
if not patch_path.exists():
    raise SystemExit(3)
with open(args.output, "w", encoding="utf-8") as fh:
    json.dump(
        {
            "case": args.case,
            "files": sorted(expected),
            "patch_exists": patch_path.exists(),
            "source_fixture_id": args.source_fixture_id,
        },
        fh,
    )
""",
        encoding="utf-8",
    )
    pack = Pack(
        id="repo-pack",
        version="0.1.0",
        description="",
        defaults={},
        cases=[case],
        scoring=None,
        path=pack_dir,
        fixtures=[fixture],
    )

    verifier_result = run_repo_task_verifier(
        pack=pack,
        case=case,
        scoring=case.scoring,  # type: ignore[arg-type]
        prepared_workspace=prepared,
        patch_path=out / patch_metadata["path"],
        output_dir=out,
        repetition=1,
        timeout_s=5.0,
    )

    assert verifier_result.repo_task == {"status": "passed", "verify_exit_code": 0}
    assert verifier_result.scoring == {"mode": "verify-script", "passed": True}
    assert json.loads((out / verifier_result.verify["path"]).read_text()) == {
        "case": "edit-repo",
        "exit_code": 0,
        "files": [
            "README.md",
            "docs/notes.md",
            "src/app.py",
            "src/utils/formatting.py",
            "tests/test_app.py",
        ],
        "passed": True,
        "patch_exists": True,
        "source_fixture_id": "repo",
    }


def test_run_repo_task_executor_internal_harness_workspace_discovery_flow(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)
    (workspace / "src").mkdir()
    (workspace / "docs").mkdir()
    (workspace / "empty").mkdir()
    (workspace / "zeta.txt").write_text("zeta\n", encoding="utf-8")
    (workspace / "src" / "app.py").write_text("print('old')\n", encoding="utf-8")
    (workspace / "docs" / "guide.md").write_text("guide\n", encoding="utf-8")

    def harness(request: AgentSessionHarnessRequest) -> AgentSessionHarnessResult:
        assert request.list_workspace_paths() == (
            "docs/guide.md",
            "src/app.py",
            "zeta.txt",
        )
        assert request.workspace_file_exists("src/app.py") is True
        assert request.workspace_file_exists("src") is False
        assert request.workspace_file_exists("missing.txt") is False
        assert request.read_workspace_text("docs/guide.md") == "guide\n"

        request.write_workspace_text("docs/created.txt", "created\n")
        request.write_workspace_text("a/new.txt", "new\n")
        if request.workspace_file_exists("a/new.txt"):
            request.write_workspace_text(
                "src/app.py",
                request.read_workspace_text("src/app.py").replace("old", "new"),
            )

        assert request.list_workspace_paths() == (
            "a/new.txt",
            "docs/created.txt",
            "docs/guide.md",
            "src/app.py",
            "zeta.txt",
        )
        return AgentSessionHarnessResult(stdout="discovered\n", stderr="")

    record = run_repo_task_executor(
        TaskExecutionRequest(
            output_dir=out,
            case=make_case(),
            repetition=1,
            workspace=workspace,
            model_output_text="",
            agent_session_harness=harness,
        )
    )

    assert record == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }
    assert (workspace / "src" / "app.py").read_text(encoding="utf-8") == (
        "print('new')\n"
    )
    assert (workspace / "docs" / "created.txt").read_text(encoding="utf-8") == (
        "created\n"
    )
    assert (workspace / "a" / "new.txt").read_text(encoding="utf-8") == "new\n"
    assert (out / record["stdout_path"]).read_text(encoding="utf-8") == (
        "discovered\n"
    )
    assert (out / record["stderr_path"]).read_text(encoding="utf-8") == ""


def test_run_repo_task_executor_internal_harness_workspace_discovery_symlinks(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    (workspace / "target.txt").write_text("target\n", encoding="utf-8")
    outside.write_text("outside\n", encoding="utf-8")
    try:
        (workspace / "inside-link.txt").symlink_to("target.txt")
        (workspace / "outside-link.txt").symlink_to(outside)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    def harness(request: AgentSessionHarnessRequest) -> AgentSessionHarnessResult:
        assert request.list_workspace_paths() == (
            "inside-link.txt",
            "target.txt",
        )
        assert request.workspace_file_exists("inside-link.txt") is True
        with pytest.raises(TaskError, match="unsafe harness workspace path"):
            request.workspace_file_exists("outside-link.txt")
        return AgentSessionHarnessResult()

    record = run_repo_task_executor(
        TaskExecutionRequest(
            output_dir=out,
            case=make_case(),
            repetition=1,
            workspace=workspace,
            model_output_text="",
            agent_session_harness=harness,
        )
    )

    assert record == {
        "stdout_path": "task/edit-repo/rep-001.stdout.log",
        "stderr_path": "task/edit-repo/rep-001.stderr.log",
    }


@pytest.mark.parametrize("relative_path", ["../outside.txt", "/tmp/outside.txt"])
def test_run_repo_task_executor_internal_harness_rejects_unsafe_workspace_read(
    tmp_path: Path,
    relative_path: str,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("source repo\n", encoding="utf-8")

    def harness(request: AgentSessionHarnessRequest) -> AgentSessionHarnessResult:
        request.read_workspace_text(relative_path)
        return AgentSessionHarnessResult()

    with pytest.raises(TaskError, match="unsafe harness workspace path"):
        run_repo_task_executor(
            TaskExecutionRequest(
                output_dir=out,
                case=make_case(),
                repetition=1,
                workspace=workspace,
                model_output_text="",
                agent_session_harness=harness,
            )
        )

    assert not (out / "task" / "edit-repo" / "rep-001.stdout.log").exists()


@pytest.mark.parametrize("relative_path", ["../outside.txt", "/tmp/outside.txt"])
def test_run_repo_task_executor_internal_harness_rejects_unsafe_workspace_exists(
    tmp_path: Path,
    relative_path: str,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)

    def harness(request: AgentSessionHarnessRequest) -> AgentSessionHarnessResult:
        request.workspace_file_exists(relative_path)
        return AgentSessionHarnessResult()

    with pytest.raises(TaskError, match="unsafe harness workspace path"):
        run_repo_task_executor(
            TaskExecutionRequest(
                output_dir=out,
                case=make_case(),
                repetition=1,
                workspace=workspace,
                model_output_text="",
                agent_session_harness=harness,
            )
        )

    assert not (out / "task" / "edit-repo" / "rep-001.stdout.log").exists()


def test_run_repo_task_executor_internal_harness_rejects_missing_workspace_read(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)

    def harness(request: AgentSessionHarnessRequest) -> AgentSessionHarnessResult:
        request.read_workspace_text("missing.txt")
        return AgentSessionHarnessResult()

    with pytest.raises(TaskError, match="could not read harness workspace file"):
        run_repo_task_executor(
            TaskExecutionRequest(
                output_dir=out,
                case=make_case(),
                repetition=1,
                workspace=workspace,
                model_output_text="",
                agent_session_harness=harness,
            )
        )

    assert not (out / "task" / "edit-repo" / "rep-001.stdout.log").exists()


def test_run_repo_task_executor_internal_harness_rejects_non_utf8_workspace_read(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)
    (workspace / "binary.dat").write_bytes(b"\xff\xfe\x00\x00")

    def harness(request: AgentSessionHarnessRequest) -> AgentSessionHarnessResult:
        request.read_workspace_text("binary.dat")
        return AgentSessionHarnessResult()

    with pytest.raises(TaskError, match="could not read harness workspace file"):
        run_repo_task_executor(
            TaskExecutionRequest(
                output_dir=out,
                case=make_case(),
                repetition=1,
                workspace=workspace,
                model_output_text="",
                agent_session_harness=harness,
            )
        )

    assert not (out / "task" / "edit-repo" / "rep-001.stdout.log").exists()


def test_run_repo_task_executor_internal_harness_rejects_unsafe_workspace_write(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)

    def harness(request: AgentSessionHarnessRequest) -> AgentSessionHarnessResult:
        request.write_workspace_text("/tmp/outside.txt", "bad\n")
        return AgentSessionHarnessResult()

    with pytest.raises(TaskError, match="unsafe harness workspace path"):
        run_repo_task_executor(
            TaskExecutionRequest(
                output_dir=out,
                case=make_case(),
                repetition=1,
                workspace=workspace,
                model_output_text="",
                agent_session_harness=harness,
            )
        )

    assert not (out / "task" / "edit-repo" / "rep-001.stdout.log").exists()


def test_run_repo_task_executor_internal_harness_rejects_non_string_logs(
    tmp_path: Path,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)

    def harness(request: AgentSessionHarnessRequest) -> AgentSessionHarnessResult:
        return AgentSessionHarnessResult(stdout=None)  # type: ignore[arg-type]

    with pytest.raises(TaskError, match="stdout/stderr must be strings"):
        run_repo_task_executor(
            TaskExecutionRequest(
                output_dir=out,
                case=make_case(),
                repetition=1,
                workspace=workspace,
                model_output_text="",
                agent_session_harness=harness,
            )
        )

    assert not (out / "task" / "edit-repo" / "rep-001.stdout.log").exists()


@pytest.mark.parametrize(
    ("model_output_text", "expected_stderr"),
    [
        (
            "No patch here.\n```python\nprint('ignored')\n```\n",
            (
                "No fenced diff or patch block found in model output; "
                "workspace left unchanged.\n"
            ),
        ),
        (
            "```diff\n--- a/README.md\n+++ b/README.md\nnot a hunk\n```\n",
            (
                "Patch rejected: unified diff could not be applied cleanly; "
                "workspace left unchanged.\n"
            ),
        ),
    ],
)
def test_run_repo_task_executor_logs_patch_outcomes_as_task_results(
    tmp_path: Path,
    model_output_text: str,
    expected_stderr: str,
) -> None:
    out = tmp_path / "run"
    workspace = out / "workspace" / "edit-repo" / "rep-001"
    workspace.mkdir(parents=True)
    (workspace / "README.md").write_text("old\n", encoding="utf-8")

    record = run_repo_task_executor(
        TaskExecutionRequest(
            output_dir=out,
            case=make_case(),
            repetition=1,
            workspace=workspace,
            model_output_text=model_output_text,
        )
    )

    assert (workspace / "README.md").read_text(encoding="utf-8") == "old\n"
    assert (out / record["stdout_path"]).read_text(encoding="utf-8") == ""
    assert (out / record["stderr_path"]).read_text(encoding="utf-8") == (
        expected_stderr
    )


def test_apply_unified_diff_to_workspace_empty_patch_logs_stderr(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    applied, stdout, stderr = apply_unified_diff_to_workspace("  \n", workspace)

    assert applied is False
    assert stdout == ""
    assert stderr == (
        "Patch rejected: fenced patch block is empty; workspace left unchanged.\n"
    )


def test_apply_unified_diff_to_workspace_missing_git_logs_stderr(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "README.md").write_text("old\n", encoding="utf-8")
    diff = (
        "--- a/README.md\n"
        "+++ b/README.md\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    def missing_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr("benchpack.tasks.subprocess.run", missing_git)

    applied, stdout, stderr = apply_unified_diff_to_workspace(diff, workspace)

    assert applied is False
    assert stdout == ""
    assert stderr == "Patch rejected: git executable not found; workspace left unchanged.\n"
    assert (workspace / "README.md").read_text(encoding="utf-8") == "old\n"


def test_apply_unified_diff_to_workspace_rejects_workspace_escape(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    diff = (
        "--- /dev/null\n"
        "+++ b/../outside.txt\n"
        "@@ -0,0 +1 @@\n"
        "+outside\n"
    )

    applied, stdout, stderr = apply_unified_diff_to_workspace(diff, workspace)

    assert applied is False
    assert stdout == ""
    assert stderr == (
        "Patch rejected: path escapes workspace: ../outside.txt; "
        "workspace left unchanged.\n"
    )
    assert not outside.exists()


def test_apply_unified_diff_to_workspace_rejects_absolute_path(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    diff = (
        "--- /dev/null\n"
        "+++ b//etc/passwd\n"
        "@@ -0,0 +1 @@\n"
        "+outside\n"
    )

    applied, stdout, stderr = apply_unified_diff_to_workspace(diff, workspace)

    assert applied is False
    assert stdout == ""
    assert stderr == (
        "Patch rejected: path escapes workspace: /etc/passwd; "
        "workspace left unchanged.\n"
    )


def test_apply_unified_diff_to_workspace_rejects_quoted_workspace_escape(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    diff = (
        "--- /dev/null\n"
        '+++ "b/foo\\057..\\057..\\057outside.txt"\n'
        "@@ -0,0 +1 @@\n"
        "+outside\n"
    )

    applied, stdout, stderr = apply_unified_diff_to_workspace(diff, workspace)

    assert applied is False
    assert stdout == ""
    assert stderr == (
        "Patch rejected: path escapes workspace: foo/../../outside.txt; "
        "workspace left unchanged.\n"
    )
    assert not outside.exists()
