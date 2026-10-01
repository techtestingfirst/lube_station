# Agent Instructions
- Source truth: user plan + tasks_spec.json decisions (custom tables, 11 types, Password field, lease table, per-plan dunning, link-table helpdesk, full portal, strict P1-P12).
- Order: strict P1-P12. Next: P1-F5 downloads, then P2 customers.
- Evidence only: run bench --site lubestation.localhost migrate + run-tests before marking done.
- Commit code + tasks_spec.json together.
- Blockers: vendor names pending for P6-F1 multi-API, P7 multi-registrar, P5 all-gateways matrix. Do not build live adapters until names land.
- Manual gates: live creds, live pay, domain reg, destructive server ops need comment+status approval.
