import frappe
from frappe.model.document import Document


class TLDPricing(Document):
    def validate(self):
        import re

        tld = (self.tld or "").strip().lower()
        if not tld.startswith("."):
            tld = f".{tld}"
        if not re.fullmatch(r"\.[a-z0-9-]+(\.[a-z0-9-]+)*", tld):
            frappe.throw("TLD looks invalid, e.g. .com or .co.in")
        self.tld = tld


def tld_of(domain: str) -> str | None:
    """Longest matching priced TLD suffix for a domain, or None (fallback rate)."""
    domain = (domain or "").strip().lower()
    if "." not in domain:
        return None
    rows = frappe.get_all("TLD Pricing", ["tld"])
    best = None
    for row in rows:
        suffix = (row.tld or "").strip().lower()
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        if domain == suffix[1:] or domain.endswith(suffix):
            if best is None or len(suffix) > len(best):
                best = suffix
    return best


def domain_price(domain: str, action: str = "register") -> float:
    """WHMCS per-TLD pricing: register/renew/transfer rate for a domain.

    Falls back per-field (blank transfer -> register rate) then to the
    `domain_year_price` setting when no TLD row matches.
    """
    from lube_station.lube_station.settings import get_setting

    fallback = get_setting("domain_year_price")
    match = tld_of(domain)
    if not match or not frappe.db.exists("TLD Pricing", match):
        return fallback
    row = frappe.db.get_value("TLD Pricing", match, ["register_price", "renew_price", "transfer_price"], as_dict=True)
    action = (action or "register").strip().lower()
    if action == "transfer":
        return row.transfer_price or row.register_price or fallback
    if action == "renew":
        return row.renew_price or row.register_price or fallback
    return row.register_price or fallback
