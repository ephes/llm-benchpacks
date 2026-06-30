from __future__ import annotations

import csv
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
        "cluster-billiger-python",
        "cluster-billiger-rust",
    ]
    assert [case.harness.id for case in pack.cases if case.harness] == [
        "external-agent",
        "external-agent",
    ]


def test_product_offer_python_stub_verifier_writes_cluster_metrics(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    shutil.copytree(PACK_DIR / "fixtures" / "billiger-matcher-repo", workspace)
    patch = tmp_path / "patch.diff"
    patch.write_text("placeholder patch\n", encoding="utf-8")
    output = tmp_path / "verify.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(PACK_DIR / "verify" / "score_clusters.py"),
            "--workspace",
            str(workspace),
            "--case",
            "cluster-billiger-python",
            "--pack-id",
            "product-offer-matching",
            "--pack-version",
            "0.1.0",
            "--source-fixture-id",
            "billiger-matcher-repo",
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
    assert payload["metrics"]["bcubed"]["precision"] == 1.0
    assert payload["metrics"]["bcubed"]["f1"] < 0.70
    assert payload["metrics"]["pairwise_cluster"]["f1"] == 0.0
    assert payload["metrics"]["eval_pair_operating_point_from_clusters"][
        "positive_prevalence"
    ] == 0.25
    assert payload["combined_score"]["formula"].startswith("100 *")
    assert payload["combined_score"]["components"]["average_precision"] > 0.0
    assert payload["thresholds"] == {
        "bcubed_f1_min": 0.7,
        "pairwise_cluster_f1_min": 0.2,
    }
    assert payload["prediction_errors"] == []
    assert payload["system_metrics"]["test_offers"] == 21825
    assert payload["system_metrics"]["eval_pairs"] == 20000


def test_product_offer_hidden_clusters_are_not_public_order_contiguous() -> None:
    labels_path = PACK_DIR / "verify" / "hidden_test_clusters.csv"
    with labels_path.open(newline="", encoding="utf-8") as handle:
        cluster_ids = [row["cluster_id"] for row in csv.DictReader(handle)]

    adjacent_same = sum(
        left == right for left, right in zip(cluster_ids, cluster_ids[1:])
    )

    assert len(cluster_ids) == 21825
    assert adjacent_same / (len(cluster_ids) - 1) < 0.01
    assert len(set(cluster_ids[:100])) > 90


def test_pi_agent_rejects_disallowed_replacement_path(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("benchpack_pi_agent", PI_AGENT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "clusterer.py").write_text("print('old')\n", encoding="utf-8")

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
        module._apply_edits(workspace, payload, ("clusterer.py",))
    except ValueError as exc:
        assert "disallowed path" in str(exc)
    else:
        raise AssertionError("expected disallowed path to be rejected")
    assert (workspace / "clusterer.py").read_text(encoding="utf-8") == "print('old')\n"


def test_pi_agent_previews_billiger_cluster_data_files(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("benchpack_pi_agent", PI_AGENT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    workspace = tmp_path / "workspace"
    data = workspace / "data"
    data.mkdir(parents=True)
    (data / "train_offers.csv").write_text(
        "offer_id,title,shop_name,price_eur,brand,category_label,cluster_id,cluster_label\n"
        "o00001,alpha,shopA,100.00,BrandA,Phones,c00001,Alpha\n"
        "o00002,beta,shopB,110.00,BrandB,Phones,c00002,Beta\n",
        encoding="utf-8",
    )
    (data / "test_offers.csv").write_text(
        "offer_id,title,shop_name,price_eur,brand,category_label\n"
        "o00003,gamma,shopC,120.00,BrandC,Phones\n",
        encoding="utf-8",
    )
    (data / "eval_pairs.csv").write_text(
        "pair_id,offer_id_left,offer_id_right\n"
        "ep000001,o00003,o00004\n",
        encoding="utf-8",
    )

    preview = module._data_context(workspace, preview_rows=1)

    assert "data/train_offers.csv" in preview
    assert "data/test_offers.csv" in preview
    assert "data/eval_pairs.csv" in preview
    assert "PREVIEW ONLY: data/train_offers.csv has 2 data rows" in preview


def test_pi_agent_repairs_truncated_final_json_container() -> None:
    spec = importlib.util.spec_from_file_location("benchpack_pi_agent", PI_AGENT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    payload = '{"files":[{"path":"clusterer.py","content":"print(\\"ok\\")\\n"}]'

    assert module._parse_edit_payload(payload) == {
        "files": [{"path": "clusterer.py", "content": 'print("ok")\n'}]
    }


def test_pi_agent_extracts_fenced_json_payload_with_preamble() -> None:
    spec = importlib.util.spec_from_file_location("benchpack_pi_agent", PI_AGENT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    payload = (
        "Here is the edit.\n\n"
        "```json\n"
        '{"files":[{"path":"clusterer.py","content":"print(\\"ok\\")\\n"}]}\n'
        "```\n"
    )

    assert module._parse_edit_payload(payload) == {
        "files": [{"path": "clusterer.py", "content": 'print("ok")\n'}]
    }
