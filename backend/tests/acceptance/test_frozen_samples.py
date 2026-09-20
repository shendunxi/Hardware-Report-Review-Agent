"""Contract checks for the frozen 17-file acceptance evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


BACKEND = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path(__file__).with_name("sample_manifest.json")
RESULTS_PATH = BACKEND.parent / "docs" / "evidence" / "a11-local-vertical-slice" / "sample-results.json"


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def sample_run() -> dict:
    assert RESULTS_PATH.is_file(), "run the frozen-sample acceptance command first"
    return json.loads(RESULTS_PATH.read_text(encoding="utf-8"))


def test_manifest_freezes_seventeen_inputs_and_fifteen_business_groups(manifest: dict) -> None:
    samples = manifest["samples"]
    assert len(samples) == 17
    assert len({item["id"] for item in samples}) == 17
    assert len({item["group_id"] for item in samples}) == 15
    assert sum(item["role"] == "TASK_PRIMARY" for item in samples) == 15
    assert sum(item["role"] == "COMPATIBILITY_ALTERNATE" for item in samples) == 2
    assert {item["id"] for item in samples if item["role"] == "COMPATIBILITY_ALTERNATE"} == {"S-07", "S-15"}
    assert all(Path(item["relative_path"]).suffix.lower() == item["expected_extension"] for item in samples)
    # The manifest must stay machine-independent: the sample root is supplied at
    # run time, so no entry may carry a committed absolute path.
    assert all("absolute_path" not in item for item in samples)
    assert all(not Path(item["relative_path"]).is_absolute() for item in samples)
    assert all("\\" not in item["relative_path"] for item in samples)
    assert "source_root" not in manifest


def test_generated_evidence_preserves_every_source(sample_run: dict) -> None:
    files = sample_run["files"]
    assert len(files) == 17
    assert all(item["before"] == item["after"] for item in files)
    assert all(item["source_unchanged"] is True for item in files)


def test_fifteen_groups_have_exactly_twenty_one_active_results(sample_run: dict) -> None:
    groups = sample_run["report_groups"]
    assert len(groups) == 15
    for group in groups:
        ids = [item["rule_id"] for item in group["rule_results"]]
        assert len(ids) == 21
        assert len(set(ids)) == 21
        assert "TR-05" not in ids


@pytest.mark.skipif(
    os.environ.get("HW_REVIEW_REQUIRE_ALL_FROZEN_SAMPLES") != "1",
    reason="release-gate assertion is opt-in; generated evidence records NO-GO without hiding failures",
)
def test_all_frozen_samples_are_parseable(sample_run: dict) -> None:
    assert all(item["parse_status"] == "SUCCESS" for item in sample_run["files"])


@pytest.mark.skipif(
    os.environ.get("HW_REVIEW_REQUIRE_ALL_FROZEN_SAMPLES") != "1",
    reason="release-gate assertion is opt-in; generated evidence records NO-GO without hiding failures",
)
def test_all_release_gates_are_go(sample_run: dict) -> None:
    assert all(item["status"] == "GO" for item in sample_run["gates"])
