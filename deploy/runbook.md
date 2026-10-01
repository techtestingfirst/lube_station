# Production Runbook

## Backups
- `bench --site lubestation.localhost backup --with-files` daily via cron.
- Retain 30 days. Test restore monthly on staging.

## Workers/Scheduler
- Monitor RQ workers + scheduler heartbeat. Alert on queue depth > 100 or stale scheduler > 5 min.
- Provisioning, webhook, dunning jobs retry with backoff + idempotency keys.

## Manual gates (human approval required)
- Live credentials, live payment mode, domain registration, destructive server actions, termination, wipe, deletion.
- Approval = comment + status on Order/Service/Domain record. No silent auto-execute.

## Go-live checklist
- Secrets in Password fields, never in logs.
- Webhook secrets configured per gateway.
- Sandbox invoice end-to-end green on staging.
- `bench --site <prod> run-tests --app lube_station` green.
