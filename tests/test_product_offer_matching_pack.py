from __future__ import annotations

import json
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

from benchpack.packs import load_pack


PACK_DIR = Path("benchpacks/product-offer-matching")
PI_AGENT_PATH = Path("examples/external-agent/pi-agent.py")


def test_product_offer_matching_pack_loads_with_external_agent_cases() -> None:
    pack = load_pack(PACK_DIR)

    assert pack.id == "product-offer-matching"
    assert [case.id for case in pack.cases] == [
        "pairwise-real-small-python",
        "pairwise-real-small-rust",
    ]
    assert [case.harness.id for case in pack.cases if case.harness] == [
        "external-agent",
        "external-agent",
    ]


def test_product_offer_python_stub_verifier_writes_metrics(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(PACK_DIR / "fixtures" / "matcher-repo", workspace)
    patch = tmp_path / "patch.diff"
    patch.write_text("placeholder patch\n", encoding="utf-8")
    output = tmp_path / "verify.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(PACK_DIR / "verify" / "score_pairwise.py"),
            "--workspace",
            str(workspace),
            "--case",
            "pairwise-real-small-python",
            "--pack-id",
            "product-offer-matching",
            "--pack-version",
            "0.1.0",
            "--source-fixture-id",
            "matcher-repo",
            "--patch",
            str(patch),
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert payload["metrics"]["f1"] == 0.0
    assert payload["metrics"]["positive_prevalence"] == 0.25
    assert payload["thresholds"] == {"f1_min": 0.7}
    assert payload["prediction_errors"] == []


def test_pi_agent_rejects_disallowed_replacement_path(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("benchpack_pi_agent", PI_AGENT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "matcher.py").write_text("print('old')\n", encoding="utf-8")

    payload = {
        "files": [
            {
                "path": "verify/hidden_labels.csv",
                "content": "pair_id,label\np0001,1\n",
            }
        ],
        "summary": "attempted hidden-label write",
    }

    try:
        module._apply_edits(workspace, payload, ("matcher.py",))
    except ValueError as exc:
        assert "disallowed path" in str(exc)
    else:
        raise AssertionError("expected disallowed path to be rejected")
    assert (workspace / "matcher.py").read_text(encoding="utf-8") == "print('old')\n"
