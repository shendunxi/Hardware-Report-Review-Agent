# A11 frozen-sample results

Run: `20260920T072513Z`  
Overall release decision: **GO**  
Files: 17; business groups: 15  
Word automation policy: `any_word_compatible`

## File matrix

| ID | Group | Role | Format | Parse | Containers | Text | Tables | Images | Seconds | Peak RSS MiB | Unchanged | Error |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| S-01 | R-01 | TASK_PRIMARY | XLS | SUCCESS | 18 | 0 | 18 | 0 | 0.374 | 379.570 | YES |  |
| S-02 | R-02 | TASK_PRIMARY | XLS | SUCCESS | 4 | 0 | 4 | 0 | 0.114 | 379.605 | YES |  |
| S-03 | R-03 | TASK_PRIMARY | XLS | SUCCESS | 14 | 0 | 14 | 0 | 0.267 | 379.621 | YES |  |
| S-04 | R-04 | TASK_PRIMARY | XLS | SUCCESS | 20 | 0 | 20 | 0 | 2.201 | 380.926 | YES |  |
| S-05 | R-05 | TASK_PRIMARY | XLS | SUCCESS | 28 | 0 | 28 | 0 | 0.661 | 380.926 | YES |  |
| S-06 | R-06 | TASK_PRIMARY | DOC | SUCCESS | 55 | 904 | 33 | 94 | 30.744 | 380.926 | YES |  |
| S-07 | R-06 | COMPATIBILITY_ALTERNATE | PDF | SUCCESS | 55 | 627 | 46 | 94 | 2.235 | 280.453 | YES |  |
| S-08 | R-07 | TASK_PRIMARY | XLS | SUCCESS | 18 | 0 | 18 | 0 | 3.103 | 380.996 | YES |  |
| S-09 | R-08 | TASK_PRIMARY | XLS | SUCCESS | 27 | 0 | 27 | 0 | 0.763 | 380.996 | YES |  |
| S-10 | R-09 | TASK_PRIMARY | XLS | SUCCESS | 5 | 0 | 5 | 0 | 0.353 | 380.973 | YES |  |
| S-11 | R-10 | TASK_PRIMARY | XLS | SUCCESS | 16 | 0 | 16 | 0 | 3.251 | 390.777 | YES |  |
| S-12 | R-11 | TASK_PRIMARY | XLS | SUCCESS | 22 | 0 | 22 | 0 | 0.715 | 410.207 | YES |  |
| S-13 | R-12 | TASK_PRIMARY | PDF | SUCCESS | 25 | 521 | 14 | 37 | 2.504 | 493.703 | YES |  |
| S-14 | R-13 | TASK_PRIMARY | DOC | SUCCESS | 43 | 1054 | 36 | 59 | 30.137 | 565.023 | YES |  |
| S-15 | R-13 | COMPATIBILITY_ALTERNATE | PDF | SUCCESS | 43 | 573 | 38 | 59 | 3.287 | 585.055 | YES |  |
| S-16 | R-14 | TASK_PRIMARY | XLS | SUCCESS | 18 | 0 | 18 | 0 | 3.148 | 388.906 | YES |  |
| S-17 | R-15 | TASK_PRIMARY | XLS | SUCCESS | 23 | 0 | 23 | 0 | 0.982 | 407.879 | YES |  |

## Business groups

| Group | Primary | Selected | Fallback | Rule status | Results | Seconds |
|---|---|---|---|---|---:|---:|
| R-01 | S-01 | S-01 | NO | SUCCESS | 21 | 0.250 |
| R-02 | S-02 | S-02 | NO | SUCCESS | 21 | 0.105 |
| R-03 | S-03 | S-03 | NO | SUCCESS | 21 | 0.103 |
| R-04 | S-04 | S-04 | NO | SUCCESS | 21 | 0.960 |
| R-05 | S-05 | S-05 | NO | SUCCESS | 21 | 0.347 |
| R-06 | S-06 | S-06 | NO | SUCCESS | 21 | 0.114 |
| R-07 | S-08 | S-08 | NO | SUCCESS | 21 | 0.879 |
| R-08 | S-09 | S-09 | NO | SUCCESS | 21 | 0.274 |
| R-09 | S-10 | S-10 | NO | SUCCESS | 21 | 0.063 |
| R-10 | S-11 | S-11 | NO | SUCCESS | 21 | 0.924 |
| R-11 | S-12 | S-12 | NO | SUCCESS | 21 | 0.280 |
| R-12 | S-13 | S-13 | NO | SUCCESS | 21 | 0.094 |
| R-13 | S-14 | S-14 | NO | SUCCESS | 21 | 0.134 |
| R-14 | S-16 | S-16 | NO | SUCCESS | 21 | 0.976 |
| R-15 | S-17 | S-17 | NO | SUCCESS | 21 | 0.295 |

## Gates

| Gate | Decision | Evidence |
|---|---|---|
| G1 Source protection | GO | 17/17 unchanged fingerprints |
| G2 Readability | GO | 17/17 parsed successfully |
| G3 Structural completeness | GO | all 17 normalized documents contain inventoried structure |
| G4 Rule completeness | GO | 15/15 groups have 21 active results |
| G5 Traceability | GO | every hard failure has evidence/missing material and every pending item has an unresolved reason |
| G6 Lifecycle | GO | backend suite passed=313 failed=0 skipped=6 recorded_at=2026-09-20T06:27:53+00:00; supplementary gate evidence accepted |
| G7 Performance | GO | all measured file parse + selected rule durations are <= 1200 seconds |
| G8 UI | GO | browser_verified=True recorded_at=2026-09-20T07:25:00+00:00 missing viewports=none; supplementary gate evidence accepted |

## Boundaries

- Historical A10/A11 values were not used as an accuracy gold standard.
- Real LLM, OCR, DOCX/XLSX real-sample compatibility, production database, authentication and formal XLS writeback remain unverified.
- A compatibility alternate may supply business-rule evidence for a paired DOC/PDF group, but it never converts a failed DOC parser input into a G2 pass.
