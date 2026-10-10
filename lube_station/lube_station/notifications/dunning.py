import frappe


def daily():
    """WHMCS dunning + renewal + domain expiry notices. Idempotent via fire()."""
    _dunning_batch()
    _domain_expiry_batch()


def _dunning_batch() -> dict:
    try:
        rows = frappe.get_all("Hosting Invoice", {"status": ["in", ["Unpaid", "Overdue"]]}, ["name"], limit=500)
    except Exception:
        return {"processed": 0}
    done = 0
    for r in rows:
        try:
            from lube_station.lube_provisioning.doctype.service.service import apply_dunning

            apply_dunning(r.name)
            done += 1
        except Exception:
            continue
    return {"processed": done}


def _domain_expiry_batch() -> dict:
    try:
        from lube_station.lube_domains.doctype.registered_domain.registered_domain import check_expiry_warnings

        return check_expiry_warnings(30)
    except Exception:
        return {"warned": 0}
