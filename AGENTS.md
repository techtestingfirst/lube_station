# Agent Instructions
- Source truth: user plan + tasks_spec.json decisions (custom tables, 11 types, Password field, lease table, per-plan dunning, link-table helpdesk, full portal, strict P1-P12).
- Order: strict P1-P12. Next: P1-F5 downloads, then P2 customers.
- Evidence only: run bench --site lubestation.localhost migrate + run-tests before marking done.
- Commit code + tasks_spec.json together.
- Blockers: vendor names pending for P6-F1 multi-API, P7 multi-registrar, P5 all-gateways matrix. Do not build live adapters until names land.
- Manual gates: live creds, live pay, domain reg, destructive server ops need comment+status approval.
- for development my back end is running on port 8000
- for development my front end is running on port 8080
- for admin username Administrator/admin
- for customer username thestockdot@gmail.com/HR&THAT0
- before generating any code go and check for referance how the erpnext and helpdesk and lms is handling that task which you want to handle take referance from erpnext and helpdesk and lms.

## IMPORTANT

Always load and user frappe-app-dev skills.
Always load and user frappe-code-review skills.
Always load and user code-style skills.
Always load and user technical-writing skills.
Always load and user ui-design skills.
Always load and user draft-security-advisory skills.
Always load and user deep-app-audit skills.
Always load and user api-development skills.
Always load and user app-development skills.
Always load and user desk-customization skills.
Always load and user doctype-development skills.
Always load and user enterprise-patterns skills.
Always load and user frappe-manager skills.
Always load and user frontend-development skills.
Always load and user printing-templates skills.
Always load and user project-triage skills.
Always load and user reports skills.
Always load and user router skills.
Always load and user testing skills.
Always load and user ui-patterns skills.
Always load and user web-forms skills.

## Development Details

Unless mentioned, the site for back end is lubestation.localhost port 8000 with Administrator/admin credentials.
Unless mentioned, the site for front end is lubestation.localhost  port 8080 with thestockdot@gmail.com/HR&THAT0 credentials.


## Planning / Spec-ing

Use Tracer bullets comes from the Pragmatic Programmer. When building systems, you want to write code that gets you feedback as quickly as possible. Tracer bullets are small slices of functionality that go through all layers of the system, allowing you to test and validate your approach early. This helps in identifying potential issues and ensures that the overall architecture is sound before investing significant time in development.

## Regression tests

* When we fix a bug, add at the very least a Unit test, and verify before/after by temp revert of fix to make sure the test tests what is intended
* do commit after every change.
