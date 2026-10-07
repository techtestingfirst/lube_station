import frappe
from frappe.model.document import Document


class TaxRule(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF
        from lube_station.lube_billing.doctype.tax_eligible_group.tax_eligible_group import TaxEligibleGroup

        active: DF.Check
        country: DF.Link | None
        eligible_groups: DF.Table[TaxEligibleGroup]
        percentage: DF.Float
        state: DF.Data | None
        tax_name: DF.Data
    # end: auto-generated types

    def validate(self):
        if (self.percentage or 0) < 0:
            frappe.throw("Percentage cannot be negative")


def matching_rules(customer: str) -> list:
    """WHMCS-style rule lookup: country/state must match customer address.

    Blank rule country/state means "all" (preserves legacy catch-all rules).
    Comparison is case-insensitive; customer state goes through GST
    normalization so "bihar" matches a "Bihar" rule; country nicknames
    ("USA") match standard names ("United States").
    """
    group = frappe.db.get_value("Hosting Customer", customer, "client_group")
    cust_country = normalize_country(frappe.db.get_value("Hosting Customer", customer, "country")).lower()
    raw_state = (frappe.db.get_value("Hosting Customer", customer, "state") or "").strip().lower()
    cust_state = normalize_state(frappe.db.get_value("Hosting Customer", customer, "state"))
    cust_state = (cust_state or "").lower()
    rules = frappe.get_all("Tax Rule", filters={"active": 1}, fields=["name"])
    out = []
    for r in rules:
        doc = frappe.get_doc("Tax Rule", r.name)
        if doc.eligible_groups:
            allowed = [g.client_group for g in doc.eligible_groups]
            if group not in allowed:
                continue
        rule_country = normalize_country(doc.country).lower()
        if rule_country and rule_country != cust_country:
            continue
        rule_state = (doc.state or "").strip().lower()
        if rule_state and rule_state not in (cust_country, cust_state, raw_state):
            continue
        out.append(doc)
    return out


def _as_lines(subtotal: float | list) -> list:
    """Normalize taxable base input: float (fully taxable, legacy callers) or
    item lines with per-item taxable flags (WHMCS per-product Apply Tax)."""
    if isinstance(subtotal, (int, float)):
        return [{"amount": float(subtotal), "taxable": True}]
    return [{"amount": float(i.get("amount") or 0), "taxable": bool(i.get("taxable", True))} for i in (subtotal or [])]


def tax_for(customer: str, subtotal: float | list) -> float:
    return tax_breakup(customer, subtotal)["total"]


def tax_breakup(customer: str, subtotal: float | list) -> dict:
    """WHMCS-pattern tax with India GST place-of-supply on top.

    1. Taxable base = only lines flagged taxable (per-product Apply Tax;
       domains per Settings; legacy float input counts fully taxable).
    2. GST mode (GST Settings seller state + recognizable customer state):
       same state -> CGST+SGST, same plain UT -> CGST+UGST, else IGST.
    3. Rules mode: match customer country/state to active Tax Rules
       (blank = all), level 1 on base, level 2 compounded on base+L1
       (WHMCS two-level behavior).
    4. Exclusive (default): tax added on top. Inclusive: backed out of the
       listed price (WHMCS: tax = price/(100+rate)*rate, extended per level).
    """
    from lube_station.lube_station.settings import get_setting

    lines = _as_lines(subtotal)
    base = round(sum(i["amount"] for i in lines if i["taxable"]), 2)
    empty = {"cgst": 0, "sgst": 0, "ugst": 0, "igst": 0, "rules": [], "total": 0, "mode": "legacy", "taxable_base": base, "label": "No tax"}
    if base <= 0:
        return empty
    gst = _gst_split(customer)
    mode = get_setting("tax_mode") or "Exclusive"
    if gst is not None:
        # GST engine owns the CGST/SGST/UGST/IGST heads. Same-named Tax Rules
        # are ignored here so sellers don't double-tax; other matching rules
        # (e.g. Cess) apply additively as extras.
        net_base = base if mode == "Exclusive" else round(base / (1 + gst["rate"] / 100), 2)
        out = _gst_parts(net_base, gst["kind"], gst["rate"])
        extras = []
        for r in matching_rules(customer):
            if (r.tax_name or "").strip().upper() in ("CGST", "SGST", "UGST", "IGST"):
                continue
            extras.append({"name": r.tax_name, "rate": r.percentage or 0, "amount": round(net_base * (r.percentage or 0) / 100, 2)})
        out["rules"] = extras
        out["total"] = round(out["total"] + sum(e["amount"] for e in extras), 2)
        out.update({"mode": "gst", "taxable_base": base})
        out["label"] = out["label"] + (" + " + " + ".join(f"{e['name']} {e['rate']}%" for e in extras) if extras else "")
        return out
    rules = matching_rules(customer)
    if not rules:
        return empty
    level1 = [r for r in rules if str(r.get("level") or "1") == "1"]
    level2 = [r for r in rules if str(r.get("level") or "1") == "2"]
    r1 = sum((r.percentage or 0) for r in level1) / 100
    r2 = sum((r.percentage or 0) for r in level2) / 100
    rule_lines = []
    if mode == "Inclusive":
        mult = (1 + r1) * (1 + r2)
        net = base / mult if mult else base
        l1_total = net * r1
        l2_total = net * (1 + r1) * r2
        for r in level1:
            rule_lines.append({"name": r.tax_name, "rate": r.percentage or 0, "amount": round(l1_total * ((r.percentage or 0) / 100) / r1, 2) if r1 else 0})
        for r in level2:
            rule_lines.append({"name": r.tax_name, "rate": r.percentage or 0, "amount": round(l2_total * ((r.percentage or 0) / 100) / r2, 2) if r2 else 0})
        total = round(l1_total + l2_total, 2)
    else:
        l1_total = base * r1
        l2_total = (base + l1_total) * r2
        for r in level1:
            rule_lines.append({"name": r.tax_name, "rate": r.percentage or 0, "amount": round(base * (r.percentage or 0) / 100, 2)})
        for r in level2:
            rule_lines.append({"name": r.tax_name, "rate": r.percentage or 0, "amount": round((base + l1_total) * (r.percentage or 0) / 100, 2)})
        total = round(l1_total + l2_total, 2)
    label = " + ".join(f"{i['name']} {i['rate']}%" for i in rule_lines) if rule_lines else "No tax"
    return {"cgst": 0, "sgst": 0, "ugst": 0, "igst": 0, "rules": rule_lines, "total": total, "mode": mode.lower(), "taxable_base": base, "label": label}


def _gst_parts(base: float, kind: str, rate: float) -> dict:
    half = round(rate / 2, 2)
    parts = {"cgst": 0, "sgst": 0, "ugst": 0, "igst": 0}
    if kind == "igst":
        parts["igst"] = round(base * rate / 100, 2)
        label = f"IGST {rate}%"
    elif kind == "ugst":
        parts["cgst"] = round(base * half / 100, 2)
        parts["ugst"] = round(base * half / 100, 2)
        label = f"CGST {half}% + UGST {half}%"
    else:
        parts["cgst"] = round(base * half / 100, 2)
        parts["sgst"] = round(base * half / 100, 2)
        label = f"CGST {half}% + SGST {half}%"
    parts["total"] = round(parts["cgst"] + parts["sgst"] + parts["ugst"] + parts["igst"], 2)
    parts["label"] = label
    return parts


# UTs without legislature: intra-UT trade draws CGST + UGST.
_UT_WITHOUT_LEGISLATURE = {
    "andaman and nicobar islands",
    "chandigarh",
    "dadra and nagar haveli and daman and diu",
    "ladakh",
    "lakshadweep",
}

_STATE_ALIASES = {
    "bihar": "Bihar",
    "up": "Uttar Pradesh",
    "uttar pradesh": "Uttar Pradesh",
    "maharashtra": "Maharashtra",
    "karnataka": "Karnataka",
    "tamil nadu": "Tamil Nadu",
    "tamilnadu": "Tamil Nadu",
    "west bengal": "West Bengal",
    "bengal": "West Bengal",
    "gujarat": "Gujarat",
    "rajasthan": "Rajasthan",
    "punjab": "Punjab",
    "haryana": "Haryana",
    "kerala": "Kerala",
    "odisha": "Odisha",
    "orissa": "Odisha",
    "assam": "Assam",
    "jharkhand": "Jharkhand",
    "chhattisgarh": "Chhattisgarh",
    "madhya pradesh": "Madhya Pradesh",
    "mp": "Madhya Pradesh",
    "andhra pradesh": "Andhra Pradesh",
    "telangana": "Telangana",
    "goa": "Goa",
    "delhi": "Delhi",
    "new delhi": "Delhi",
    "nct of delhi": "Delhi",
    "jammu and kashmir": "Jammu and Kashmir",
    "jammu & kashmir": "Jammu and Kashmir",
    "j&k": "Jammu and Kashmir",
    "puducherry": "Puducherry",
    "pondicherry": "Puducherry",
    "chandigarh": "Chandigarh",
    "ladakh": "Ladakh",
    "lakshadweep": "Lakshadweep",
    "andaman and nicobar islands": "Andaman and Nicobar Islands",
    "andaman": "Andaman and Nicobar Islands",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
}


_CANONICAL_STATES = {
    "andaman and nicobar islands": "Andaman and Nicobar Islands",
    "andhra pradesh": "Andhra Pradesh",
    "arunachal pradesh": "Arunachal Pradesh",
    "assam": "Assam",
    "bihar": "Bihar",
    "chandigarh": "Chandigarh",
    "chhattisgarh": "Chhattisgarh",
    "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "delhi": "Delhi",
    "goa": "Goa",
    "gujarat": "Gujarat",
    "haryana": "Haryana",
    "himachal pradesh": "Himachal Pradesh",
    "jammu and kashmir": "Jammu and Kashmir",
    "jharkhand": "Jharkhand",
    "karnataka": "Karnataka",
    "kerala": "Kerala",
    "ladakh": "Ladakh",
    "lakshadweep": "Lakshadweep",
    "madhya pradesh": "Madhya Pradesh",
    "maharashtra": "Maharashtra",
    "manipur": "Manipur",
    "meghalaya": "Meghalaya",
    "mizoram": "Mizoram",
    "nagaland": "Nagaland",
    "odisha": "Odisha",
    "puducherry": "Puducherry",
    "punjab": "Punjab",
    "rajasthan": "Rajasthan",
    "sikkim": "Sikkim",
    "tamil nadu": "Tamil Nadu",
    "telangana": "Telangana",
    "tripura": "Tripura",
    "uttar pradesh": "Uttar Pradesh",
    "uttarakhand": "Uttarakhand",
    "west bengal": "West Bengal",
}


def normalize_state(raw: str | None) -> str | None:
    if not raw:
        return None
    key = " ".join(str(raw).strip().lower().split())
    if key in _STATE_ALIASES:
        return _STATE_ALIASES[key]
    return _CANONICAL_STATES.get(key)


_COUNTRY_ALIASES = {
    "usa": "United States",
    "us": "United States",
    "u.s.a.": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
}


def normalize_country(raw: str | None) -> str:
    """Standard name for a country nickname; unknown values pass through."""
    if not raw:
        return ""
    key = " ".join(str(raw).strip().lower().split())
    return _COUNTRY_ALIASES.get(key, str(raw).strip())


def _gst_split(customer: str) -> dict | None:
    """India-domestic place of supply. Skipped unless both sides are India."""
    try:
        seller_state = frappe.db.get_single_value("GST Settings", "seller_state")
        seller_country = (frappe.db.get_single_value("GST Settings", "seller_country") or "India").strip().lower()
        rate = frappe.db.get_single_value("GST Settings", "gst_rate") or 0
    except Exception:
        return None
    if not seller_state or not rate:
        return None
    if seller_country not in ("india", "bharat", ""):
        return None
    buyer_country = (frappe.db.get_value("Hosting Customer", customer, "country") or "").strip().lower()
    if buyer_country and buyer_country not in ("india", "bharat"):
        return None
    seller = normalize_state(seller_state)
    buyer = normalize_state(frappe.db.get_value("Hosting Customer", customer, "state"))
    if not seller or not buyer:
        return None
    if seller != buyer:
        return {"kind": "igst", "rate": rate}
    if buyer.lower() in _UT_WITHOUT_LEGISLATURE:
        return {"kind": "ugst", "rate": rate}
    return {"kind": "sgst", "rate": rate}
