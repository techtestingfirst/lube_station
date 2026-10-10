import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date, now_datetime, today


class RegisteredDomain(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        auto_renew: DF.Check
        customer: DF.Link | None
        domain_name: DF.Data
        expiry_date: DF.Date | None
        last_checked: DF.Datetime | None
        nameservers: DF.SmallText | None
        premium_price: DF.Currency
        registrar: DF.Link | None
        registration_date: DF.Date | None
        status: DF.Literal["Available", "Taken", "Premium", "Unknown", "Registered", "Expired", "Transferred"]
        whois_privacy: DF.Check
    # end: auto-generated types

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
    if frappe.db.exists("Registered Domain", domain):
        frappe.db.set_value("Registered Domain", domain, {"status": result["status"], "last_checked": now_datetime()})
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
            result = {"domain": domain, "status": status, "premium_price": out.get("premium_price", 0)}
            try:
                from lube_station.lube_domains.doctype.tld_pricing.tld_pricing import domain_price

                result["pricing"] = {
                    "register": domain_price(domain, "register"),
                    "renew": domain_price(domain, "renew"),
                    "transfer": domain_price(domain, "transfer"),
                }
            except Exception:
                pass
            return result
        except Exception:
            pass
    return {"domain": domain, "status": "Available", "premium_price": 0}


def _adapter_for(domain_name: str, registrar: str | None = None):
    from lube_station.lube_station.adapters.registry import get_registrar_adapter

    dom = frappe.get_doc("Registered Domain", domain_name) if frappe.db.exists("Registered Domain", domain_name) else None
    name = registrar or (dom.registrar if dom and dom.registrar else None)
    if not name:
        for candidate in ["OpenSRS", "Namecheap", "GoDaddy", "ResellerClub / LogicBoxes"]:
            if frappe.db.get_value("Registrar Adapter", candidate, "active"):
                name = candidate
                break
    if not name:
        frappe.throw("No active registrar")
    return get_registrar_adapter(name), name


def _notify_domain(customer: str | None, event_type: str, domain: str, extra: dict | None = None):
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        ctx = {"domain": domain}
        if extra:
            ctx.update(extra)
        notify_customer(customer, event_type, domain, ctx)
    except Exception:
        pass


@frappe.whitelist(methods=["POST"])
def register_domain(domain: str, customer: str | None = None, registrar: str | None = None, years: int = 1) -> dict:
    if not customer or not frappe.db.exists("Hosting Customer", customer):
        frappe.throw("Customer is required: order the domain through the cart so it is invoiced")
    adapter, name = _adapter_for(domain, registrar)
    out = adapter.register_domain(domain, {}, [])
    if not frappe.db.exists("Registered Domain", domain):
        frappe.get_doc({"doctype": "Registered Domain", "domain_name": domain, "customer": customer, "registrar": name, "registration_date": today(), "expiry_date": add_to_date(today(), years=years), "status": "Registered"}).insert(ignore_permissions=True)
    else:
        frappe.db.set_value("Registered Domain", domain, {"status": "Registered", "registrar": name, "expiry_date": add_to_date(today(), years=years)})
    _notify_domain(customer, "domain_registered", domain, {"registrar": name, "years": years})
    return {"registered": domain, "vendor": out}


@frappe.whitelist(methods=["POST"])
def renew_domain(domain: str, years: int = 1) -> dict:
    from lube_station.lube_domains.doctype.tld_pricing.tld_pricing import domain_price

    adapter, name = _adapter_for(domain)
    out = adapter.renew_domain(domain, years)
    if frappe.db.exists("Registered Domain", domain):
        dom = frappe.get_doc("Registered Domain", domain)
        base = dom.expiry_date or today()
        dom.expiry_date = add_to_date(base, years=years)
        dom.save(ignore_permissions=True)
        if dom.customer:
            rate = domain_price(domain, "renew")
            try:
                frappe.get_doc({"doctype": "Hosting Invoice", "customer": dom.customer, "invoice_items": [{"description": f"Domain renewal {domain} x{years}y", "service_ref": domain, "amount": rate * years}], "status": "Unpaid", "idempotency_key": f"domain-renew:{domain}:{dom.expiry_date}"}).insert(ignore_permissions=True)
            except Exception:
                pass
            _notify_domain(dom.customer, "domain_renewal", f"{domain}:{dom.expiry_date}", {"expiry": str(dom.expiry_date), "years": years})
            _notify_domain(dom.customer, "domain_renewed", f"{domain}:{dom.expiry_date}", {"expiry": str(dom.expiry_date), "years": years})
    return {"renewed": domain, "vendor": out}


@frappe.whitelist(methods=["POST"])
def transfer_domain(domain: str, auth_code: str, registrar: str | None = None, customer: str | None = None) -> dict:
    if not customer or not frappe.db.exists("Hosting Customer", customer):
        frappe.throw("Customer is required: order the domain through the cart so it is invoiced")
    adapter, name = _adapter_for(domain, registrar)
    _notify_domain(customer, "domain_transfer_initiated", domain, {"registrar": name})
    out = adapter.transfer_domain(domain, auth_code)
    if frappe.db.exists("Registered Domain", domain):
        frappe.db.set_value("Registered Domain", domain, {"status": "Transferred", "registrar": name})
    else:
        try:
            frappe.get_doc({"doctype": "Registered Domain", "domain_name": domain, "customer": customer, "registrar": name, "status": "Transferred"}).insert(ignore_permissions=True)
        except Exception:
            pass
    _notify_domain(customer, "domain_transfer_completed", domain, {"registrar": name})
    return {"transferred": domain, "vendor": out}


@frappe.whitelist(methods=["POST"])
def update_nameservers(domain: str, nameservers: list | str) -> dict:
    adapter, _ = _adapter_for(domain)
    if isinstance(nameservers, str):
        nameservers = [n.strip() for n in nameservers.split(",")]
    out = adapter.update_nameservers(domain, nameservers)
    customer = None
    if frappe.db.exists("Registered Domain", domain):
        frappe.db.set_value("Registered Domain", domain, "nameservers", ",".join(nameservers))
        try:
            customer = frappe.db.get_value("Registered Domain", domain, "customer")
        except Exception:
            pass
    _notify_domain(customer, "domain_ns_update", f"{domain}:ns", {"nameservers": ",".join(nameservers)})
    return {"domain": domain, "vendor": out}


def check_expiry_warnings(days_ahead: int = 30) -> dict:
    """WHMCS expiry notices: warn for domains expiring within window."""
    from frappe.utils import add_days as _add_days

    try:
        cutoff = _add_days(today(), days_ahead)
        rows = frappe.get_all("Registered Domain", {"status": ["in", ["Registered", "Transferred"]], "expiry_date": ["<=", cutoff]}, ["name", "customer", "expiry_date"])
    except Exception:
        return {"warned": 0}
    warned = 0
    for r in rows:
        try:
            from lube_station.lube_station.notifications.events import notify_customer

            notify_customer(r.customer, "domain_expiry_warning", f"{r.name}:{r.expiry_date}", {"domain": r.name, "expiry": str(r.expiry_date)})
            warned += 1
        except Exception:
            continue
    return {"warned": warned}


def subdomain_suffixes() -> list:
    """Seller-configured free-subdomain suffixes (one per line in Settings)."""
    from lube_station.lube_station.settings import get_setting

    raw = get_setting("free_subdomain_suffixes") or ""
    return [line.strip().lower().lstrip(".") for line in str(raw).splitlines() if line.strip()]


def validate_subdomain(name: str) -> str:
    """WHMCS free-subdomain parity: prefix + seller suffix, unique across
    Registered Domain rows and Service primary domains. Returns the normalized name."""
    import re

    name = (name or "").strip().lower()
    suffixes = subdomain_suffixes()
    if not suffixes:
        frappe.throw("Free subdomains are not offered")
    if not re.fullmatch(r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+", name or ""):
        frappe.throw("Enter a valid subdomain")
    if not any(name.endswith(f".{s}") for s in suffixes):
        frappe.throw("Subdomain must use an offered suffix")
    if frappe.db.exists("Registered Domain", name) or frappe.db.exists("Service", {"primary_domain": name}):
        frappe.throw("That subdomain is already taken")
    return name
