import json

import frappe
from frappe.model.document import Document


class ProductTypeSchema(Document):
    def validate(self):
        keys = [f.field_key for f in self.fields]
        if len(keys) != len(set(keys)):
            frappe.throw("Duplicate field_key in schema")


def _schema_doc(name: str):
    doc = frappe.get_doc("Product Type Schema", name)
    return doc


def _missing(config: dict, aliases: list) -> bool:
    for key in aliases:
        value = config.get(key)
        if isinstance(value, str):
            value = value.strip()
        if value not in (None, ""):
            return False
    return True


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _option_pricing(field) -> tuple:
    """Parse a requirement field's Options JSON into (allowed, prices, per_unit, checked_price).

    Shapes (all optional-price; plain string lists mean no delta):
    - ["a", "b"] -> allowed {a, b}, no prices
    - [{"label": "Extra 50GB", "value": "ssd-50", "price": 5}] -> allowed + deltas
      (`price_delta` / `amount` accepted as aliases for `price`)
    - {"ssd-50": 5, "ssd-100": 9} -> allowed keys + deltas
    - {"price_per_unit": 2} -> Integer/Decimal fields bill value x 2
    - {"price": 5} -> Checkbox fields bill 5 when checked
    """
    raw = field.get("options_json")
    if not raw:
        return None, {}, None, None
    try:
        options = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None, {}, None, None
    if isinstance(options, list):
        allowed: set = set()
        prices: dict = {}
        for entry in options:
            if isinstance(entry, str):
                allowed.add(entry)
                continue
            if isinstance(entry, dict) and entry.get("value") is not None:
                key = str(entry["value"])
                allowed.add(key)
                amount = _num(entry.get("price", entry.get("price_delta", entry.get("amount"))))
                if amount:
                    prices[key] = amount
        return allowed or None, prices, None, None
    if isinstance(options, dict):
        per_unit = _num(options.get("price_per_unit"))
        if per_unit:
            return None, {}, per_unit, None
        if _num(options.get("price")) is not None and len(options) == 1:
            return None, {}, None, float(options["price"])
        allowed = set()
        prices = {}
        for key, spec in options.items():
            if key in ("price", "price_delta", "amount", "price_per_unit", "label"):
                continue
            allowed.add(str(key))
            if isinstance(spec, dict):
                amount = _num(spec.get("price", spec.get("price_delta", spec.get("amount"))))
            else:
                amount = _num(spec)
            if amount:
                prices[str(key)] = amount
        return allowed or None, prices, None, None
    return None, {}, None, None


def _is_checked(value) -> bool:
    return value in (1, True, "1", "true", "True", "yes", "on", "checked")


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and "," in value:
        return [part.strip() for part in value.split(",") if part.strip()]
    text = str(value).strip()
    return [text] if text else []


def option_price_delta(schema_name: str, config: dict) -> float:
    """WHMCS Configurable Options: sum of per-option price deltas for a config.

    Server-authoritative: cart recalc and invoices use this, never client totals.
    Unknown fields and free-text fields contribute 0.
    """
    doc = _schema_doc(schema_name)
    config = config or {}
    total = 0.0
    for f in doc.fields:
        key = f.get("field_key")
        if key not in config or config[key] in (None, ""):
            continue
        allowed, prices, per_unit, checked_price = _option_pricing(f)
        ftype = f.get("field_type")
        if ftype == "Select":
            total += prices.get(str(config[key]).strip(), 0)
        elif ftype == "Multi Select":
            for choice in _as_list(config[key]):
                total += prices.get(choice, 0)
        elif ftype == "Checkbox":
            if _is_checked(config[key]) and checked_price:
                total += checked_price
        elif ftype in ("Integer", "Decimal"):
            amount = _num(config[key])
            if amount and per_unit:
                total += amount * per_unit
    return round(total, 2)


# Canonical config keys per WHMCS Server/VPS order fields. Aliases keep
# older schemas (e.g. root_pass) working while the portal writes canonical keys.
_FLAG_ALIASES = {
    "requires_hostname": [["hostname"]],
    "requires_root_password": [["root_password", "root_pass", "rootpw"]],
    "requires_os": [["os", "os_image", "image"]],
    "requires_location": [["location", "datacenter", "region"]],
}

_NS1_ALIASES = ["ns1", "nameserver1", "ns_prefix_1"]
_NS2_ALIASES = ["ns2", "nameserver2", "ns_prefix_2"]


def validate_config(schema_name: str, config: dict, domain: str | None = None):
    doc = _schema_doc(schema_name)
    config = config or {}
    for f in doc.fields:
        value = config.get(f.field_key)
        if isinstance(value, str):
            value = value.strip()
        if f.required and value in (None, ""):
            frappe.throw(f"Missing required field: {f.field_key}")
        # Closed option sets reject unknown values (price-tamper guard:
        # deltas are computed server-side, so an off-list value bills 0).
        if value not in (None, "") and f.field_type in ("Select", "Multi Select"):
            allowed, _prices, _per_unit, _checked = _option_pricing(f)
            if allowed:
                choices = _as_list(value) if f.field_type == "Multi Select" else [str(value).strip()]
                if any(c not in allowed for c in choices):
                    frappe.throw(f"Invalid option for {f.field_key}")
    # WHMCS parity: schema flags are enforced, not UI hints. A flag without a
    # matching field row still rejects empty input (portal renders canonical keys).
    for flag, groups in _FLAG_ALIASES.items():
        if getattr(doc, flag, 0) and all(_missing(config, aliases) for aliases in groups):
            frappe.throw(f"Missing required field: {groups[0][0]}")
    if getattr(doc, "requires_nameservers", 0):
        if _missing(config, _NS1_ALIASES) or _missing(config, _NS2_ALIASES):
            frappe.throw("Missing required field: ns1 / ns2")
    if getattr(doc, "requires_domain", 0):
        effective = (domain or "").strip() or (config.get("_domain") or "").strip() or (config.get("domain") or "").strip()
        if not effective:
            frappe.throw("Missing required field: domain")
    return True


@frappe.whitelist(methods=["GET", "POST"])
def get_product_requirements(plan: str | None = None, schema: str | None = None, product_type: str | None = None):
    """Return requirement fields for checkout renderer.

    Prefers explicit schema, else resolves via Hosting Plan -> product_type_schema,
    else via product_type lookup. Validates nothing, only returns definition.
    """
    schema_name = schema
    if not schema_name and plan and frappe.db.exists("Hosting Plan", plan):
        schema_name = frappe.db.get_value("Hosting Plan", plan, "product_type_schema")
    if not schema_name and product_type:
        schema_name = frappe.db.get_value("Product Type Schema", {"product_type": product_type}, "name")
    if not schema_name:
        frappe.throw("Provide schema, plan with linked schema, or product_type")
    doc = _schema_doc(schema_name)
    return {
        "schema": doc.name,
        "product_type": doc.product_type,
        "flags": {
            "requires_domain": doc.requires_domain,
            "requires_hostname": doc.requires_hostname,
            "requires_root_password": doc.requires_root_password,
            "requires_os": doc.requires_os,
            "requires_location": doc.requires_location,
            "requires_nameservers": doc.requires_nameservers,
        },
        "fields": [
            {
                "field_key": f.field_key,
                "label": f.label,
                "field_type": f.field_type,
                "options_source": f.options_source,
                "options_json": json.loads(f.options_json) if f.options_json else None,
                "required": f.required,
                "validation_rule": f.validation_rule,
                "maps_to": f.maps_to,
            }
            for f in doc.fields
        ],
    }
