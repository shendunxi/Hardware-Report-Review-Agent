# Task 9 — frozen 17-file acceptance and release gates

## Outcome

Task 9 implementation is complete, but the local vertical slice is **NO-GO for release**. Run `20260916T014614Z` produced six GO gates and two NO-GO gates. G2 and G3 remain NO-GO because the host does not provide genuine Microsoft Word: both `.doc` task primaries fail with `DOC_CONVERSION_FAILED`, and the registered `Word.Application` server resolves to Kingsoft WPS. WPS evidence is not accepted as Microsoft Word compatibility.

The paired PDFs were used only as compatibility alternates for the two affected business groups. They allow all 15 business groups to exercise the rule engine, but they do not turn the two failed DOC parser inputs into a readability pass.

## Frozen matrix results

| Measure | Result |
|---|---:|
| Parser inputs | 17 |
| Business groups | 15 |
| Parsed inputs | 15/17 |
| Source fingerprints unchanged | 17/17 |
| Groups with exactly 21 active results | 15/15 |
| TR-05 independent results | 0 |
| Compatibility fallbacks used | 2 |
| Automated backend suite | 282 passed, 6 skipped |
| Frontend contract suite | 44 passed |

The six skips are explicit: four existing genuine-Word acceptance skips plus the two opt-in hard release-gate assertions. With `HW_REVIEW_REQUIRE_ALL_FROZEN_SAMPLES=1`, the gate suite intentionally reports `3 passed, 2 failed`, proving that the release blocker is executable and not hidden.

## Gate decisions

| Gate | Decision | Evidence |
|---|---|---|
| G1 Source protection | GO | 17/17 independent post-run SHA-256, size and mtime fingerprints match |
| G2 Readability | NO-GO | 15/17 inputs parsed; S-06 and S-14 DOC failed without genuine Word |
| G3 Structural completeness | NO-GO | the two failed DOC inputs have no normalized structure |
| G4 Rule completeness | GO | all 15 business groups produced 21 unique active results and no TR-05 result |
| G5 Traceability | GO | every hard failure has located evidence or missing-material facts; every pending result has an unresolved reason |
| G6 Lifecycle | GO | Task 7 focused 45 pass and prior full backend 274 pass / 4 skips |
| G7 Performance | GO | all measured parse plus selected-rule durations are below 1,200 seconds |
| G8 UI | GO | Task 8 real browser flow plus 1440x900, 1280x720 and 760x900 checks |

## Defects found and corrected

The first matrix run parsed only 13/17 inputs. S-03 and S-05 failed because real workbook sheet names `温升 ` and `DCDC ` end with a space: the domain base model stripped the space while the parser preserved it in structural addresses, violating the sheet-prefix invariant. A regression test now proves exact trailing-space preservation, and `DocumentContainer.name_or_number` explicitly opts out of global string trimming. The XLS/parser contract suite then passed 23/23, and the second matrix run parsed both files.

The acceptance runner also initially recorded zero duration for failed parses. A failure-path test now proves that elapsed time and peak RSS are retained even when parsing raises. Final DOC failure measurements are present in `sample-results.json`.

## Exact verification commands

```powershell
Set-Location 'E:\Coding\Hardware-Report-Review-Agent\backend'
$env:PYTHONPATH='src'
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m hw_review.acceptance.run_samples --manifest tests/acceptance/sample_manifest.json --output ../docs/evidence/a11-local-vertical-slice
& 'C:\Users\sdt52153\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q --basetemp .pytest-task9-full

Set-Location 'E:\Coding\Hardware-Report-Review-Agent\prototype\a11-ui'
node --check app.js
node --check api-client.js
node --test tests/prototype.test.js
```

Acceptance runner exit code `1` is expected while the overall decision is NO-GO. After the final API parser-registration correction, the normal full suite passed `282 passed, 6 skipped`; Node passed `44/44`.

## Product-copy scan

No product UI contains `无法判断`, `接受例外` or `A111`. The only backend product match is the approved TR-16 wording `不设置严重性`, which states the prohibition rather than introducing a severity field. Other matches are negative tests, invalid-input fixtures, requirements or prior audit records.

## Evidence package

- Machine-readable matrix: `docs/evidence/a11-local-vertical-slice/sample-results.json`
- Human-readable matrix: `docs/evidence/a11-local-vertical-slice/sample-results.md`
- Gate summary: `docs/evidence/a11-local-vertical-slice/release-gates.md`
- Lifecycle evidence: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-7-report.md`
- Browser evidence: `.superpowers/sdd/2026-09-11-a11-local-vertical-slice/task-8-report.md`

## Release blockers and deferred boundaries

Before G2/G3 can become GO, rerun the same frozen matrix on a host with genuine Microsoft Word and obtain 17/17 successful parses with unchanged source fingerprints. Real LLM calls, OCR, DOCX/XLSX real-sample compatibility, production database selection, authentication/authorization and formal A11 XLS writeback remain unverified and are not claimed by this slice.
