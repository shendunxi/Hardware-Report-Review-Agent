# Acceptance Reproducibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the frozen 17-file acceptance matrix runnable from any checkout by resolving samples from an externally supplied root instead of absolute paths committed in the manifest.

**Architecture:** The manifest keeps only `relative_path`; the runner resolves it against a root supplied by `--sample-root` or `HW_REVIEW_SAMPLE_ROOT`, refusing absolute paths and upward traversal. Generated evidence records the supplied values verbatim so committed artifacts carry no machine paths.

**Tech Stack:** Python 3.12, pytest.

**Spec:** `docs/superpowers/specs/2026-09-20-acceptance-reproducibility-design.md`

## Global Constraints

- Do not add test files or test cases; extend existing test bodies only.
- Do not perform Git operations.
- Do not change gate count, gate semantics or the 17-file / 15-group invariants.
- Do not change parsers, rules, lifecycle or the staging pipeline.
- `_parse_samples` must keep working for a 1-sample manifest (existing unit test calls it directly).
- Do not leak an absolute sample root into committed evidence.

---

### Task 1: Resolve samples from an external root

**Files:** Modify `acceptance/run_samples.py`.

**Interfaces:** `resolve_sample_path(sample_root: Path, relative_path: str) -> Path`; `_parse_samples(manifest, output_dir, *, sample_root: Path)`.

- [x] Add `SAMPLE_ROOT_ENV = "HW_REVIEW_SAMPLE_ROOT"` and the portable-separator helper.
- [x] Add `resolve_sample_path` rejecting absolute paths, drive letters, `..` segments and post-resolve escapes.
- [x] Replace both `Path(sample["absolute_path"])` call sites with the resolver.
- [x] Record per-file `SOURCE` / `INVALID_SAMPLE_PATH` failures instead of aborting the loop.

### Task 2: Validate the manifest up front

**Files:** Modify `acceptance/run_samples.py` (`_load_manifest`, `run`).

**Interfaces:** `_load_manifest(path: Path, sample_root: Path) -> dict`; `run(manifest_path, output_dir, *, sample_root)`.

- [x] Keep the 17-sample, 15-group and unique-id checks unchanged.
- [x] Resolve every entry in `_load_manifest` so a malformed manifest fails fast.
- [x] Thread `sample_root` through `run`.

### Task 3: De-identify the generated evidence

**Files:** Modify `acceptance/run_samples.py` (`run`).

- [x] Replace `source_root` with `sample_root`, recording the supplied value without `resolve()`.
- [x] Record `manifest` as supplied, not resolved.
- [x] Raise `schema_version` to `1.1`.

### Task 4: CLI contract

**Files:** Modify `acceptance/run_samples.py` (`main`).

- [x] Add `--sample-root`.
- [x] Fall back to `HW_REVIEW_SAMPLE_ROOT`.
- [x] Fail with an actionable message naming both options when neither is supplied.

### Task 5: Rewrite the manifest and update the callers

**Files:** Modify `tests/acceptance/sample_manifest.json`, `tests/acceptance/test_frozen_samples.py`, `tests/acceptance/test_acceptance_runner.py`, `README.md`.

- [x] Rewrite the manifest: drop `source_root` and every `absolute_path`; use `/` separators; keep all 17 ids, groups, roles and extensions identical.
- [x] Update the frozen-sample manifest assertions to validate `relative_path` instead of `absolute_path`.
- [x] Update the runner unit test for the new `_parse_samples` signature.
- [x] Update the README acceptance section to describe `--sample-root`.

### Task 6: Prove portability with a placeholder tree

**Files:** Create `docs/evidence/acceptance-reproducibility/verification.md`; update this plan.

- [x] Extend the runner test to assert an absolute or traversing `relative_path` is refused.
- [x] Extend the runner test to assert a missing sample root raises rather than silently passing.
- [x] Run the full backend suite and record the exact result.
- [x] Generate a placeholder tree (17 files, 15 groups, 2 alternates) outside the repo, run the real CLI against it, and confirm `sample-results.json` / `sample-results.md` / `release-gates.md` are produced with no machine path in the output.
- [x] Record the deliberate deferral of the G6/G8 evidence restructuring to S4.
