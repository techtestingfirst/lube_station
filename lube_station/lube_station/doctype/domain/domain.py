import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class Domain(Document):
    pass


RATE_LIMIT = 30
CACHE_TTL = 600


def _rate_limit_ok() -> bool:
    user = frappe.session.user
    key = f"domain-avail-rl:{user}"
    count = frappe.cache().get_value(key) or 0
    if count >= RATE_LIMIT:
        return False
    frappe.cache().set_value(key, count + 1, expires_in_sec=60)
    return True


@frappe.whitelist(methods=["GET", "POST"])
def check_availability(domain: str, registrar: str | None = None) -> dict:
    domain = (domain or "").strip().lower()
    if not domain or "." not in domain:
        frappe.throw("Invalid domain")
    if not _rate_limit_ok():
        frappe.throw("Rate limit exceeded, try later")
    cache_key = f"domain-avail:{domain}:{registrar or 'default'}"
    cached = frappe.cache().get_value(cache_key)
    if cached:
        return cached
    result = _lookup(domain, registrar)
    frappe.cache().set_value(cache_key, result, expires_in_sec=CACHE_TTL)
    if frappe.db.exists("Domain", domain):
        frappe.db.set_value("Domain", domain, {"status": result["status"], "last_checked": now_datetime()})
    return result


def _lookup(domain: str, registrar: str | None) -> dict:
    from lube_station.lube_station.adapters.registry import get_registrar_adapter

    name = registrar
    if not name:
        for candidate in ["OpenSRS", "Namecheap", "GoDaddy", "ResellerClub / LogicBoxes"]:
            if frappe.db.get_value("Registrar Adapter", candidate, "active"):
                name = candidate
                break
    if name:
        try:
            adapter = get_registrar_adapter(name)
            out = adapter.check_availability(domain)
            status = out.get("status", "unknown").capitalize()
            if status not in ("Available", "Taken", "Premium"):
                status = "Unknown"
            return {"domain": domain, "status": status, "premium_price": out.get("premium_price", 0)}
        except Exception:
            pass
    return {"domain": domain, "status": "Available", "premium_price": 0}
