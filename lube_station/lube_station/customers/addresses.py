"""Customer address book on Frappe core Address + Dynamic Links.

Multiple addresses per Hosting Customer (Billing/Shipping/...). Ownership is
guarded through the Dynamic Link table; reads use get_all (ignores perms,
server-side logic) exactly like the wallet and support proxies. Exactly one
primary billing and one shipping default, enforced server-side.
"""

import frappe

from lube_station.lube_station.portal.guards import assert_owns, my_customer

ADDRESS_FIELDS = [
    "name",
    "address_title",
    "address_type",
    "address_line1",
    "address_line2",
    "city",
    "state",
    "country",
    "pincode",
    "phone",
    "is_primary_address",
    "is_shipping_address",
    "disabled",
]

TYPES = ("Billing", "Shipping", "Office", "Personal", "Other")


def _owns(customer: str, name: str) -> None:
    if not frappe.db.exists(
        "Dynamic Link",
        {"parent": name, "parenttype": "Address", "link_doctype": "Hosting Customer", "link_name": customer},
    ):
        frappe.throw("Unknown address", frappe.DoesNotExistError)
    assert_owns(customer)


def _clear_flag(customer: str, field: str) -> None:
    for row in frappe.db.get_all(
        "Address",
        {
            "name": ["in", _linked_names(customer)],
            field: 1,
        },
        ["name"],
    ):
        frappe.db.set_value("Address", row["name"], field, 0)


def _linked_names(customer: str) -> list:
    return frappe.db.get_all(
        "Dynamic Link",
        {"parenttype": "Address", "link_doctype": "Hosting Customer", "link_name": customer},
        pluck="parent",
    ) or ["__none__"]


@frappe.whitelist(methods=["GET"])
def my_addresses() -> list:
    customer = my_customer()
    return frappe.db.get_all(
        "Address",
        {"name": ["in", _linked_names(customer)], "disabled": 0},
        ADDRESS_FIELDS,
        order_by="is_primary_address desc, modified desc",
    )


def _clean(data: dict) -> dict:
    out = {}
    for key in (
        "address_title",
        "address_type",
        "address_line1",
        "address_line2",
        "city",
        "state",
        "country",
        "pincode",
        "phone",
    ):
        if data.get(key) is None:
            continue
        val = str(data[key]).strip()
        if key == "country" and val and not frappe.db.exists("Country", val):
            frappe.throw("Select a valid country")
        if key == "address_type" and val and val not in TYPES:
            frappe.throw("Select a valid address type")
        out[key] = val[:140]
    return out


@frappe.whitelist(methods=["POST"])
def add_address(
    address_title: str,
    address_line1: str,
    city: str,
    country: str,
    address_type: str = "Billing",
    address_line2: str | None = None,
    state: str | None = None,
    pincode: str | None = None,
    phone: str | None = None,
    is_primary: bool | None = None,
    is_shipping: bool | None = None,
) -> dict:
    customer = my_customer()
    for label, val in (("Title", address_title), ("Address line", address_line1), ("City", city), ("Country", country)):
        if not (val or "").strip():
            frappe.throw(f"{label} required", frappe.MandatoryError)
    first = not frappe.db.get_all(
        "Address",
        {"name": ["in", _linked_names(customer)], "disabled": 0},
        limit=1,
    )
    doc = frappe.get_doc(
        {
            "doctype": "Address",
            **_clean(
                {
                    "address_title": address_title,
                    "address_type": address_type or "Billing",
                    "address_line1": address_line1,
                    "address_line2": address_line2,
                    "city": city,
                    "state": state,
                    "country": country,
                    "pincode": pincode,
                    "phone": phone,
                }
            ),
            "links": [{"link_doctype": "Hosting Customer", "link_name": customer}],
        }
    ).insert(ignore_permissions=True)
    # First address, or explicit request, becomes the default(s).
    if first or _flag(is_primary):
        _clear_flag(customer, "is_primary_address")
        frappe.db.set_value("Address", doc.name, "is_primary_address", 1)
    if first or _flag(is_shipping):
        _clear_flag(customer, "is_shipping_address")
        frappe.db.set_value("Address", doc.name, "is_shipping_address", 1)
    return {"address": doc.name}


@frappe.whitelist(methods=["POST"])
def update_address(
    name: str,
    address_title: str | None = None,
    address_type: str | None = None,
    address_line1: str | None = None,
    address_line2: str | None = None,
    city: str | None = None,
    state: str | None = None,
    country: str | None = None,
    pincode: str | None = None,
    phone: str | None = None,
    is_primary: bool | None = None,
    is_shipping: bool | None = None,
) -> dict:
    customer = my_customer()
    _owns(customer, name)
    data = _clean(
        {
            "address_title": address_title,
            "address_type": address_type,
            "address_line1": address_line1,
            "address_line2": address_line2,
            "city": city,
            "state": state,
            "country": country,
            "pincode": pincode,
            "phone": phone,
        }
    )
    doc = frappe.get_doc("Address", name)
    doc.update(data)
    doc.save(ignore_permissions=True)
    if _flag(is_primary):
        _clear_flag(customer, "is_primary_address")
        frappe.db.set_value("Address", name, "is_primary_address", 1)
    if _flag(is_shipping):
        _clear_flag(customer, "is_shipping_address")
        frappe.db.set_value("Address", name, "is_shipping_address", 1)
    return {"address": name}


def _flag(value) -> bool:
    return value is True or value == 1 or str(value).strip().lower() in ("1", "true", "yes")


@frappe.whitelist(methods=["POST"])
def set_default_address(name: str, kind: str = "billing") -> dict:
    customer = my_customer()
    _owns(customer, name)
    field = "is_shipping_address" if kind == "shipping" else "is_primary_address"
    _clear_flag(customer, field)
    frappe.db.set_value("Address", name, field, 1)
    return {"address": name, "kind": kind}


@frappe.whitelist(methods=["POST"])
def delete_address(name: str) -> dict:
    customer = my_customer()
    _owns(customer, name)
    was_primary = bool(frappe.db.get_value("Address", name, "is_primary_address"))
    was_shipping = bool(frappe.db.get_value("Address", name, "is_shipping_address"))
    frappe.db.set_value("Address", name, "disabled", 1)
    # Deleting a default promotes the most recent remaining address.
    remaining = frappe.db.get_all(
        "Address",
        {"name": ["in", _linked_names(customer)], "disabled": 0},
        ["name"],
        order_by="modified desc",
        limit=1,
    )
    if remaining:
        if was_primary:
            frappe.db.set_value("Address", remaining[0]["name"], "is_primary_address", 1)
        if was_shipping:
            frappe.db.set_value("Address", remaining[0]["name"], "is_shipping_address", 1)
    return {"deleted": name}


def billing_address_text(customer: str) -> str | None:
    """Default billing Address rendered, or None when the customer has none.

    Used for invoice 'Billed to' blocks; callers fall back to the legacy
    single-address fields on Hosting Customer.
    """
    try:
        from frappe.contacts.doctype.address.address import get_default_address

        name = get_default_address("Hosting Customer", customer)
        if not name:
            return None
        a = frappe.db.get_value(
            "Address",
            name,
            ["address_line1", "address_line2", "city", "state", "pincode", "country", "phone"],
            as_dict=True,
        )
        if not a:
            return None
        lines = [
            a.get("address_line1") or "",
            a.get("address_line2") or "",
            ", ".join(p for p in (a.get("city"), a.get("state")) if p),
            " ".join(p for p in (a.get("pincode"), a.get("country")) if p),
        ]
        text = "\n".join(line.strip() for line in lines if line.strip())
        if a.get("phone"):
            text += f"\n{a['phone']}"
        return text or None
    except Exception:
        return None
