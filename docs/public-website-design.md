# Public Website — Design Record

## Understanding

- Public site plus portal for hosting sales. Self-serve first, lead-gen second.
- Hybrid: Jinja marketing at `/ /pricing /hosting /domains /support`, Vue portal at `/portal`.
- All 11 product types sell Day 1. Prices read live from Hosting Plan plus Plan Pricing.
- Backend is `lube_station` P1-P12. Pay runs through Frappe Payments. Support runs through Helpdesk HD Ticket plus link table.
- Guests browse, sign up, check out, pay, get provisioned. Guests send pre-sales to tickets.
- Team edits pricing often. Single VPS best-effort. No bypass of Payments or HD.

Non-goals: affiliates, promos, blog, auto-migration, custom billing UI.

## Assumptions

- Frappe session auth. Gateway tokens only. No card store.
- Domain check uses cached rate-limited lookup. Register and transfer run after pay.
- Speed target: marketing LCP under 2s cached, checkout API under 3s.
- Scale default: under 1k visits per day on one bench.
- Build refs: ERPNext cart and checkout, Helpdesk ticket portal, LMS portal auth.

## Decisions

- Hybrid Thin over full-Jinja and headless SPA. Reuse P13-F1. SEO plus app UX. Low upkeep.
- No bypass: Frappe Payments for pay, HD Ticket link table for support.
- Guest pre-sales honors `HD Settings.allow_anyone_to_create_tickets`. Throttle 10 per hour per IP. Admin-elevated insert only, because HD `tag_first_ticket` needs Tag Link read.
- Custom pay paths (webhook, bank approve, PayU, CCAvenue, saved method) share `_fulfill_order` with live path. Fulfill on Paid transition only. Retries stay idempotent.
- Home and support pages cacheable. Pricing, hosting, domains, portal boot stay `no_cache` (live data, per-session boot).
- Hosting categories cover all 11 types. Migration and downloadable map to ticket and portal delivery.

## Final design

### Architecture

- Jinja `lube_station/www/`: `home`, `pricing`, `hosting`, `domains`, `support`, `portal` boot. Guest OK except portal boot.
- Vue `frontend/src/pages/`: auth-only portal. Router guard sends guests to login. Store, cart, checkout, invoices, services, domains, DNS, downloads, support.
- Server `lube_station/lube_station/portal/apis.py`: guest `storefront` and `domain_check`, authed cart, order, invoice, service, domain APIs. Owner checks in `guards.py`.
- Services stay server-side: cart, order snapshot, idempotent invoice, payment link, provision job, registrar adapter, dunning per plan.

### Data flow

- Guest browses cached Jinja, searches domains, clicks Order, signs up, lands in portal cart.
- Checkout: cart recalc server-side, order snapshot, invoice idempotent, Payments link, webhook verify, success fulfills order, fail falls back to saved method then dunning.
- Renew: renewal invoice, pay, unsuspend. Overdue suspends. Terminate queues approval.
- Domain: search, order item, register, renew, transfer, NS update.
- Support: guest pre-sales creates unlinked ticket. Client creates linked ticket with service context plus SLA clock.
- Team edit: DocType change, migrate hook clears cache, no restart.

### Errors

- Cart totals recalc server-side. Client numbers ignored. Coupon limits enforced.
- Invoice idempotent per order plus cycle. Webhook signature first, dedupe second.
- Provision retries plus audit log, manual adapter fallback, never silent Active.
- Domain taken, premium, rate-limit cached. Registrar fail leaves order Pending Review, no capture.
- Pay fail tries saved method, then dunning grace to suspend. Terminate needs approval.
- Guest ticket spam: validation plus throttle. No PII in page cache.
- Permissions: owner filter on customer and invoice. Deny as 403 without leaking rows.

### Edges

- Downloadable checks entitlement after full pay only. Migration creates ticket task, no auto-provision.
- VPS and dedicated race on lease table lock. Wipe confirm before Available.
- Multi-cycle pricing plus multi-tax plus credit-note order fixed.
- Domain transfer plus renewal overlap handled. NS update async.
- Mid-checkout price edit: order snapshot frozen, new carts take new price.
- Single VPS crash: jobs resume, webhook replay safe, backup plus runbook.
- Dev 8080 proxies API to bench 8000. Cookies SameSite, CSRF token, no custom JWT.

### Tests

- Unit: cart totals, coupon limits, invoice idempotent, webhook dedupe, entitlement, lease lock, SLA link.
- Contract: guest storefront, domain check states, hosting filter all 11, portal auth-only, order to provision.
- E2E: guest to paid service, overdue to unsuspend, guest ticket to HD, price edit keeps snapshot.
- Gates: `bench --site lubestation.localhost migrate` plus `run-tests` green before done. Manual gates for live creds, live pay, domain reg, destructive ops.

## Status

- Built: guest pre-sales endpoint plus form, unified fulfillment paths, 11-type categories, cache split, spec fix.
- Evidence: presales 3, fulfill 2, webhook 1, autocharge 1, paylink 1, verify 3, hdlink 1, public 5 — all OK.
- Open: live gateway keys, live domain registrar, production CDN and backup drill. Each needs explicit approval.
