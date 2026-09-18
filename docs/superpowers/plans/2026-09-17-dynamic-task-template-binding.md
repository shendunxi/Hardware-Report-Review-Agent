# Dynamic task-template binding implementation plan

1. [x] Add failing domain/persistence tests for frozen template binding and migration compatibility.
2. [x] Add migration `0003`, task binding fields, serialization, and repository round trips.
3. [x] Add failing lifecycle/API tests for published-only selection and frozen enabled-rule sets.
4. [x] Bind task creation to a published template and evaluate against its immutable snapshot.
5. [x] Generalize result-set validation, manual decisions, completion and export to the task snapshot.
6. [x] Add failing frontend tests for published-template selection and request payload.
7. [x] Implement real-mode template selection and dynamic rule totals.
8. [x] Run migration, backend/frontend regression and live HTTP smoke checks; record evidence.
