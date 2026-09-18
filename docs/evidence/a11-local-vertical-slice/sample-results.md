# A11 frozen-sample results

Run: `20260916T014614Z`  
Overall release decision: **NO-GO**  
Files: 17; business groups: 15

## File matrix

| ID | Group | Role | Format | Parse | Containers | Text | Tables | Images | Seconds | Peak RSS MiB | Unchanged | Error |
|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|
| S-01 | R-01 | TASK_PRIMARY | XLS | SUCCESS | 18 | 0 | 18 | 0 | 0.325 | 510.344 | YES |  |
| S-02 | R-02 | TASK_PRIMARY | XLS | SUCCESS | 4 | 0 | 4 | 0 | 0.101 | 491.852 | YES |  |
| S-03 | R-03 | TASK_PRIMARY | XLS | SUCCESS | 14 | 0 | 14 | 0 | 0.149 | 491.863 | YES |  |
| S-04 | R-04 | TASK_PRIMARY | XLS | SUCCESS | 20 | 0 | 20 | 0 | 1.513 | 492.262 | YES |  |
| S-05 | R-05 | TASK_PRIMARY | XLS | SUCCESS | 28 | 0 | 28 | 0 | 0.360 | 492.262 | YES |  |
| S-06 | R-06 | TASK_PRIMARY | DOC | FAILED | 0 | 0 | 0 | 0 | 0.039 | 167.746 | YES | PARSING/DOC_CONVERSION_FAILED |
| S-07 | R-06 | COMPATIBILITY_ALTERNATE | PDF | SUCCESS | 55 | 627 | 46 | 94 | 1.158 | 492.266 | YES |  |
| S-08 | R-07 | TASK_PRIMARY | XLS | SUCCESS | 18 | 0 | 18 | 0 | 1.485 | 492.266 | YES |  |
| S-09 | R-08 | TASK_PRIMARY | XLS | SUCCESS | 27 | 0 | 27 | 0 | 0.406 | 492.270 | YES |  |
| S-10 | R-09 | TASK_PRIMARY | XLS | SUCCESS | 5 | 0 | 5 | 0 | 0.061 | 492.246 | YES |  |
| S-11 | R-10 | TASK_PRIMARY | XLS | SUCCESS | 16 | 0 | 16 | 0 | 1.649 | 492.270 | YES |  |
| S-12 | R-11 | TASK_PRIMARY | XLS | SUCCESS | 22 | 0 | 22 | 0 | 0.648 | 492.273 | YES |  |
| S-13 | R-12 | TASK_PRIMARY | PDF | SUCCESS | 25 | 521 | 14 | 37 | 1.899 | 492.277 | YES |  |
| S-14 | R-13 | TASK_PRIMARY | DOC | FAILED | 0 | 0 | 0 | 0 | 0.037 | 391.160 | YES | PARSING/DOC_CONVERSION_FAILED |
| S-15 | R-13 | COMPATIBILITY_ALTERNATE | PDF | SUCCESS | 43 | 573 | 38 | 59 | 2.603 | 492.281 | YES |  |
| S-16 | R-14 | TASK_PRIMARY | XLS | SUCCESS | 18 | 0 | 18 | 0 | 2.947 | 498.000 | YES |  |
| S-17 | R-15 | TASK_PRIMARY | XLS | SUCCESS | 23 | 0 | 23 | 0 | 0.612 | 518.238 | YES |  |

## Business groups

| Group | Primary | Selected | Fallback | Rule status | Results | Seconds |
|---|---|---|---|---|---:|---:|
| R-01 | S-01 | S-01 | NO | SUCCESS | 21 | 0.399 |
| R-02 | S-02 | S-02 | NO | SUCCESS | 21 | 0.106 |
| R-03 | S-03 | S-03 | NO | SUCCESS | 21 | 0.088 |
| R-04 | S-04 | S-04 | NO | SUCCESS | 21 | 0.920 |
| R-05 | S-05 | S-05 | NO | SUCCESS | 21 | 0.293 |
| R-06 | S-06 | S-07 | YES | SUCCESS | 21 | 0.133 |
| R-07 | S-08 | S-08 | NO | SUCCESS | 21 | 1.026 |
| R-08 | S-09 | S-09 | NO | SUCCESS | 21 | 0.291 |
| R-09 | S-10 | S-10 | NO | SUCCESS | 21 | 0.062 |
| R-10 | S-11 | S-11 | NO | SUCCESS | 21 | 0.983 |
| R-11 | S-12 | S-12 | NO | SUCCESS | 21 | 0.283 |
| R-12 | S-13 | S-13 | NO | SUCCESS | 21 | 0.098 |
| R-13 | S-14 | S-15 | YES | SUCCESS | 21 | 0.161 |
| R-14 | S-16 | S-16 | NO | SUCCESS | 21 | 0.992 |
| R-15 | S-17 | S-17 | NO | SUCCESS | 21 | 0.274 |

## Gates

| Gate | Decision | Evidence |
|---|---|---|
| G1 Source protection | GO | 17/17 unchanged fingerprints |
| G2 Readability | NO-GO | 15/17 parsed successfully |
| G3 Structural completeness | NO-GO | one or more inputs lack a successful normalized structure |
| G4 Rule completeness | GO | 15/15 groups have 21 active results |
| G5 Traceability | GO | every hard failure has evidence/missing material and every pending item has an unresolved reason |
| G6 Lifecycle | GO | Task 7 focused 45 pass and full backend 274 pass / 4 skips |
| G7 Performance | GO | all measured file parse + selected rule durations are <= 1200 seconds |
| G8 UI | GO | Task 8 real browser flow and 1440x900/1280x720/760x900 checks passed |

## Boundaries

- Historical A10/A11 values were not used as an accuracy gold standard.
- Real LLM, OCR, DOCX/XLSX real-sample compatibility, production database, authentication and formal XLS writeback remain unverified.
- A compatibility alternate may supply business-rule evidence for a paired DOC/PDF group, but it never converts a failed DOC parser input into a G2 pass.
