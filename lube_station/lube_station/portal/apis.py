import json

import frappe

from .guards import assert_owns, my_customer

# Keys that must never reach the customer portal. WHMCS parity: root
# passwords, tokens, API secrets and IPMI credentials stay Admin Only.
_SECRET_KEY_HINTS = ("password", "passwd", "pass", "token", "secret", "api_key", "apikey", "private_key")


def _is_secret_key(key: str) -> bool:
    lowered = (key or "").strip().lower()
    return any(hint in lowered for hint in _SECRET_KEY_HINTS)


def _sanitize_snapshot(snapshot: dict | None, schema_fields: list | None = None) -> dict:
    """Split an Order Item configuration snapshot into safe portal rows.

    Returns {"configuration": [...], "custom_fields": [...], "hidden_count": n}.
    Secret values (Password field_type or secret-looking keys) are counted
    but never returned. Follows ERPNext portal pattern: server decides
    visibility, frontend only renders.
    """
    snapshot = snapshot or {}
    by_key = {}
    if schema_fields:
        for f in schema_fields:
            by_key[f.get("field_key")] = f
    configuration: list = []
    custom_fields: list = []
    hidden = 0
    for key in sorted(snapshot.keys()):
        value = snapshot.get(key)
        if key == "_domain":
            if value not in (None, ""):
                configuration.append({"key": "domain", "label": "Domain", "value": value})
            continue
        if key.startswith("_"):
            continue
        if _is_secret_key(key):
            hidden += 1
            continue
        schema_field = by_key.get(key)
        if schema_field and (schema_field.get("field_type") == "Password" or _is_secret_key(schema_field.get("maps_to") or "")):
            hidden += 1
            continue
        if value in (None, ""):
            continue
        label = (schema_field.get("label") if schema_field else None) or key.replace("_", " ").title()
        row = {"key": key, "label": label, "value": value}
        if schema_field:
            custom_fields.append(row)
        else:
            configuration.append(row)
    return {"configuration": configuration, "custom_fields": custom_fields, "hidden_count": hidden}


def _service_snapshot(service_name: str, order_ref: str | None, plan_name: str | None) -> dict:
    """Immutable config snapshot for the service's order line (plan match preferred)."""
    if not order_ref:
        return {}
    try:
        order_doc = frappe.get_doc("Order", order_ref)
    except Exception:
        return {}
    fallback: dict = {}
    for item in order_doc.get("items") or []:
        if item.get("item_type") != "Hosting Plan":
            continue
        raw = item.get("configuration_snapshot") or "{}"
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else dict(raw)
        except Exception:
            parsed = {}
        if item.get("reference") == plan_name:
            return parsed
        if not fallback:
            fallback = parsed
    return fallback


def _adapter_for_plan(plan_name: str | None):
    """Provisioning adapter instance for a plan, or None (manual/no module)."""
    if not plan_name or not frappe.db.exists("Hosting Plan", plan_name):
        return None
    module_name = frappe.db.get_value("Hosting Plan", plan_name, "provisioning_module")
    if not module_name or not frappe.db.exists("Provisioning Module", module_name):
        return None
    try:
        module_doc = frappe.get_doc("Provisioning Module", module_name)
        from lube_station.lube_station.adapters.registry import get_provisioning_adapter

        adapter_name = module_doc.get("provisioning_adapter") or module_doc.get("control_panel")
        if not adapter_name:
            return None
        return get_provisioning_adapter(adapter_name)
    except Exception:
        return None


def _adapter_overrides(adapter, method: str) -> bool:
    """True when the adapter implements method beyond the base contract."""
    from lube_station.lube_station.adapters.provisioning.base import ProvisioningAdapter

    return getattr(type(adapter), method, None) is not getattr(ProvisioningAdapter, method, None)


def _panel_url_for(server_name: str | None, control_panel: str | None = None) -> str | None:
    """Control-panel login URL without secrets (no SSO token until live creds land)."""
    if not server_name or not frappe.db.exists("Server", server_name):
        return None
    try:
        server_doc = frappe.get_doc("Server", server_name)
    except Exception:
        return None
    host = (server_doc.get("ip_address") or server_doc.get("hostname") or "").strip()
    if not host:
        return None
    panel = control_panel or server_doc.get("control_panel") or ""
    ports = {"cPanel / WHM": 2083, "Plesk": 8443, "DirectAdmin": 2222}
    port = ports.get(panel)
    if not port:
        return f"https://{host}"
    return f"https://{host}:{port}"


def _server_has_api_user(server_name: str | None) -> bool:
    if not server_name or not frappe.db.exists("Server", server_name):
        return False
    try:
        return bool((frappe.get_doc("Server", server_name).get("api_username") or "").strip())
    except Exception:
        return False


def _client_area_for(svc, adapter) -> dict:
    if adapter is None:
        return {"panels": [], "buttons": []}
    try:
        area = adapter.get_client_area(svc.name)
        if not isinstance(area, dict):
            return {"panels": [], "buttons": []}
        buttons = [b for b in (area.get("buttons") or []) if isinstance(b, dict) and b.get("url", b.get("action"))]
        return {"panels": area.get("panels") or [], "buttons": buttons}
    except Exception:
        return {"panels": [], "buttons": []}


def _can_sso(svc, adapter) -> bool:
    """Server decides SSO visibility; frontend only renders."""
    if not svc or svc.get("status") != "Active":
        return False
    if adapter is None or not _adapter_overrides(adapter, "create_sso_session"):
        return False
    return _server_has_api_user(svc.get("server"))


def _sso_rate_ok(service: str) -> bool:
    key = f"panel-sso:{service}:{frappe.session.user}"
    count = frappe.cache().get_value(key) or 0
    if count >= 10:
        return False
    frappe.cache().set_value(key, count + 1, expires_in_sec=3600)
    return True


def _upgrade_options(plan_name: str | None, billing_cycle: str | None) -> list:
    """Same product_type, active, other plans with pricing for the cycle."""
    if not plan_name or not frappe.db.exists("Hosting Plan", plan_name):
        return []
    product_type = frappe.db.get_value("Hosting Plan", plan_name, "product_type")
    if not product_type:
        return []
    options = []
    plans = frappe.get_all(
        "Hosting Plan",
        {"product_type": product_type, "is_active": 1, "name": ["!=", plan_name]},
        ["name", "plan_name"],
    )
    for p in plans:
        price = frappe.db.get_value(
            "Plan Pricing", {"hosting_plan": p.name, "billing_cycle": billing_cycle}, ["recurring_amount", "setup_fee"]
        )
        if not price:
            continue
        recurring, setup = price
        options.append(
            {"plan": p.name, "plan_name": p.plan_name, "recurring_amount": recurring or 0, "setup_fee": setup or 0}
        )
    return sorted(options, key=lambda o: o["recurring_amount"])


_CYCLE_DAYS = {
    "Monthly": 30,
    "Quarterly": 91,
    "Semi-Annually": 182,
    "Annually": 365,
    "Biennially": 730,
    "Triennially": 1095,
    "One Time": 30,
}


def _cycle_days(cycle: str | None) -> int:
    return _CYCLE_DAYS.get(cycle or "Monthly", 30)


def _remaining_days(svc) -> int:
    """Days left in the current cycle (ERPNext Subscription prorata style)."""
    from frappe.utils import date_diff, getdate, today

    try:
        due = svc.get("next_due_date")
        if not due:
            return _cycle_days(svc.get("billing_cycle"))
        return max(0, date_diff(getdate(due), getdate(today())))
    except Exception:
        return _cycle_days(svc.get("billing_cycle"))


def _upgrade_quote(svc, new_plan: str) -> dict:
    """Prorated balance for a plan change.

    ERPNext Subscription pattern: (new - old) * remaining / cycle_days,
    plus positive setup-fee difference. Positive total needs payment before
    the swap; zero/negative swaps immediately (credit for the negative part).
    """
    cycle = svc.get("billing_cycle") or "Monthly"
    old_plan = svc.get("hosting_plan")
    old_rec = frappe.db.get_value("Plan Pricing", {"hosting_plan": old_plan, "billing_cycle": cycle}, "recurring_amount") or 0
    new_rec = frappe.db.get_value("Plan Pricing", {"hosting_plan": new_plan, "billing_cycle": cycle}, "recurring_amount") or 0
    old_setup = frappe.db.get_value("Plan Pricing", {"hosting_plan": old_plan, "billing_cycle": cycle}, "setup_fee") or 0
    new_setup = frappe.db.get_value("Plan Pricing", {"hosting_plan": new_plan, "billing_cycle": cycle}, "setup_fee") or 0
    cycle_days = _cycle_days(cycle)
    remaining = _remaining_days(svc)
    prorated = round((float(new_rec or 0) - float(old_rec or 0)) * remaining / cycle_days, 2) if cycle_days else 0.0
    setup_diff = round(max(float(new_setup or 0) - float(old_setup or 0), 0.0), 2)
    total = round(prorated + setup_diff, 2)
    return {
        "old_plan": old_plan,
        "new_plan": new_plan,
        "billing_cycle": cycle,
        "old_recurring": float(old_rec or 0),
        "new_recurring": float(new_rec or 0),
        "cycle_days": cycle_days,
        "remaining_days": remaining,
        "prorated_diff": prorated,
        "setup_diff": setup_diff,
        "total_due": total,
        "payment_required": total > 0,
    }


def _apply_plan_swap(service_name: str, new_plan: str, credit_amount: float = 0, invoice_name: str | None = None) -> dict:
    """Swap hosting plan immediately. Idempotent. No new table (comment trail)."""
    svc = frappe.get_doc("Service", service_name)
    old_plan = svc.get("hosting_plan")
    if old_plan == new_plan:
        return {"applied": True, "already": True}
    cycle = svc.get("billing_cycle") or "Monthly"
    new_rec = frappe.db.get_value("Plan Pricing", {"hosting_plan": new_plan, "billing_cycle": cycle}, "recurring_amount")
    if new_rec is None:
        new_rec = svc.get("recurring_amount") or 0
    svc.hosting_plan = new_plan
    svc.recurring_amount = new_rec
    svc.save(ignore_permissions=True)
    credit_note = None
    if (credit_amount or 0) > 0:
        try:
            cn = frappe.get_doc(
                {
                    "doctype": "Credit Note",
                    "customer": svc.get("customer"),
                    "amount": round(float(credit_amount), 2),
                    "reason": f"Downgrade credit: {service_name} {old_plan} -> {new_plan}",
                    "reference_invoice": invoice_name,
                }
            ).insert(ignore_permissions=True)
            try:
                cn.submit()
            except Exception:
                pass
            credit_note = cn.name
        except Exception:
            credit_note = None
    try:
        svc.add_comment(
            "Comment",
            f"Plan changed via portal: {old_plan} -> {new_plan}"
            + (f" (invoice {invoice_name})" if invoice_name else " (no payment needed)")
            + (f" (credit {credit_note})" if credit_note else ""),
        )
    except Exception:
        pass
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        notify_customer(
            svc.get("customer"),
            "upgrade",
            f"{service_name}:{new_plan}",
            {"service": service_name, "from": old_plan, "to": new_plan, "invoice": invoice_name or ""},
        )
    except Exception:
        pass
    # Best-effort provisioning package change; never fails the swap.
    # Manual gate: no live effect until provider creds land.
    try:
        adapter = _adapter_for_plan(new_plan)
        if adapter is not None and _adapter_overrides(adapter, "change_package"):
            adapter.change_package(service_name, new_plan)
    except Exception:
        pass
    try:
        from lube_station.lube_station.provisioning.jobs import run_change_package

        run_change_package(service_name, new_plan=new_plan, key=f"upgrade:{service_name}:{new_plan}")
    except Exception:
        pass
    return {"applied": True, "from": old_plan, "to": new_plan, "credit_note": credit_note}


def _is_staff() -> bool:
    return "System Manager" in frappe.get_roles()


def _assert_cart_access(cart_doc):
    if _is_staff():
        return
    mine = my_customer()
    if cart_doc.customer and cart_doc.customer != mine:
        frappe.throw("Cross-customer access denied", frappe.PermissionError)


def _open_cart(customer: str):
    """Latest open cart for customer with no Order yet, else new one.

    ERPNext pattern: server resolves the single open quotation/party cart,
    frontend never invents identity. Deterministic order so refresh and
    multi-step flows always land on the same cart. Carts with items win
    over freshly created empty ones, so a blank cart never shadows real
    selections after refresh.
    """
    carts = frappe.get_all("Cart", {"customer": customer}, ["name"], order_by="modified desc, creation desc", limit=20)
    open_carts = [c.name for c in carts if not frappe.db.exists("Order", {"source_cart": c.name})]
    for name in open_carts:
        if frappe.db.count("Cart Item", {"parent": name}):
            return frappe.get_doc("Cart", name)
    for name in open_carts:
        return frappe.get_doc("Cart", name)
    return frappe.get_doc({"doctype": "Cart", "customer": customer}).insert(ignore_permissions=True)


def _cart_row(cart_doc, row: str):
    """Row belonging to this cart, else loud error (never silent no-op)."""
    for item in cart_doc.items or []:
        if item.name == row:
            return item
    frappe.throw("Cart item not found in this cart. Please re-add the plan.")


def _cart_view(cart_doc) -> dict:
    return {
        "cart": cart_doc.name,
        "customer": cart_doc.customer,
        "coupon_code": cart_doc.coupon_code,
        "subtotal": cart_doc.subtotal or 0,
        "discount_total": cart_doc.discount_total or 0,
        "grand_total": cart_doc.grand_total or 0,
        "items": [
            {
                "row": i.name,
                "item_type": i.item_type,
                "hosting_plan": i.hosting_plan,
                "billing_cycle": i.billing_cycle,
                "domain": i.domain,
                "parent_service": i.get("parent_service"),
                "quantity": i.quantity,
                "unit_price": i.unit_price or 0,
                "configuration_json": i.configuration_json,
            }
            for i in (cart_doc.items or [])
        ],
    }


@frappe.whitelist(methods=["GET"], allow_guest=True)
def storefront():
    plans = frappe.get_all("Hosting Plan", {"is_active": 1}, ["name", "plan_name", "product_type", "product_group"])
    out = []
    for p in plans:
        prices = frappe.get_all("Plan Pricing", {"hosting_plan": p.name}, ["billing_cycle", "recurring_amount", "setup_fee"])
        out.append({**p, "prices": prices})
    return out


@frappe.whitelist(methods=["GET"])
def dashboard():
    customer = my_customer()
    return {
        "services": frappe.db.count("Service", {"customer": customer}),
        "unpaid": frappe.db.count("Hosting Invoice", {"customer": customer, "status": "Unpaid"}),
        "domains": frappe.db.count("Registered Domain", {"customer": customer}),
        "tickets": frappe.db.count("Ticket Hosting Reference", {"customer": customer}),
    }


@frappe.whitelist(methods=["GET", "POST"])
def checkout_info(plan: str):
    schema = frappe.db.get_value("Hosting Plan", plan, "product_type_schema")
    prices = frappe.get_all("Plan Pricing", {"hosting_plan": plan}, ["billing_cycle", "recurring_amount", "setup_fee"])
    requirements = None
    if schema:
        from lube_station.lube_catalog.doctype.product_type_schema.product_type_schema import get_product_requirements

        requirements = get_product_requirements(plan=plan)
    meta = frappe.db.get_value("Hosting Plan", plan, ["plan_name", "product_type", "product_group"], as_dict=True) or {}
    return {"prices": prices, "requirements": requirements, "plan": meta}


@frappe.whitelist(methods=["GET"])
def my_invoices():
    customer = my_customer()
    return frappe.get_all("Hosting Invoice", {"customer": customer}, ["name", "total_due", "status", "due_date", "gateway"])


@frappe.whitelist(methods=["GET"])
def my_invoice_detail(invoice: str):
    inv = frappe.get_doc("Hosting Invoice", invoice)
    assert_owns(inv.customer)
    cust = frappe.get_doc("Hosting Customer", inv.customer)
    contact = frappe.db.get_value("User", cust.user, ["full_name", "email"], as_dict=True) or {}
    address = cust.billing_address or ", ".join(
        p for p in (cust.address_line1, cust.city, cust.state, cust.postcode, cust.country) if p
    )
    data = inv.as_dict()
    data["invoice_items"] = _enriched_items(inv)
    return {
        "invoice": data,
        "customer": {
            "name": contact.get("full_name") or cust.user,
            "email": contact.get("email") or cust.user,
            "company": cust.company,
            "phone": cust.phone,
            "tax_id": cust.tax_id,
            "address": address,
        },
    }


def _enriched_items(inv):
    """Resolve each line's plan name and purchased domain.

    service_ref varies by source: Service ID (renewals/overage), Hosting
    Plan ID (orders/upgrades/setup fees), or bare domain (domain lines).
    Never raises: falls back to raw description on any miss.
    """
    order_map = {}
    if inv.order_ref and frappe.db.exists("Order", inv.order_ref):
        try:
            for oi in frappe.get_doc("Order", inv.order_ref).items:
                try:
                    snap = json.loads(oi.configuration_snapshot or "{}")
                except Exception:
                    snap = {}
                order_map.setdefault(
                    oi.reference, {"item_type": oi.item_type, "domain": snap.get("_domain")}
                )
        except Exception:
            pass
    out = []
    for it in inv.invoice_items:
        ref = (it.service_ref or "").strip()
        plan_name, domain = "", ""
        try:
            if ref and frappe.db.exists("Service", ref):
                svc = frappe.db.get_value("Service", ref, ["hosting_plan", "primary_domain"], as_dict=True)
                if svc:
                    domain = svc.get("primary_domain") or ""
                    if svc.get("hosting_plan"):
                        plan_name = frappe.db.get_value("Hosting Plan", svc["hosting_plan"], "plan_name") or ""
            if not plan_name and ref and frappe.db.exists("Hosting Plan", ref):
                plan_name = frappe.db.get_value("Hosting Plan", ref, "plan_name") or ""
            entry = order_map.get(ref)
            if entry:
                domain = domain or entry.get("domain") or ""
                if not plan_name and entry.get("item_type") == "Domain":
                    plan_name = "Domain"
            if not domain and ref and frappe.db.exists("Registered Domain", {"domain_name": ref}):
                domain = ref
                plan_name = plan_name or "Domain"
        except Exception:
            pass
        d = it.as_dict()
        d["plan_name"] = plan_name
        d["domain"] = domain
        out.append(d)
    return out


@frappe.whitelist(methods=["GET"])
def my_services():
    customer = my_customer()
    return frappe.get_all("Service", {"customer": customer}, ["name", "hosting_plan", "status", "next_due_date"])


@frappe.whitelist(methods=["GET"])
def my_service_detail(service: str):
    svc = frappe.get_doc("Service", service)
    assert_owns(svc.customer)
    fields = (
        "name",
        "customer",
        "hosting_plan",
        "order_ref",
        "billing_cycle",
        "server",
        "primary_domain",
        "svc_username",
        "status",
        "next_due_date",
        "recurring_amount",
    )
    detail = {f: svc.get(f) for f in fields}
    # Registration date: WHMCS "Registration/Order date" column.
    detail["registration_date"] = str(svc.get("creation") or "")[:10] or None

    plan = None
    plan_name = svc.get("hosting_plan")
    if plan_name and frappe.db.exists("Hosting Plan", plan_name):
        plan_doc = frappe.get_doc("Hosting Plan", plan_name)
        detail["plan_name"] = plan_doc.get("plan_name") or plan_name
        detail["product_type"] = plan_doc.get("product_type")
        detail["product_group"] = plan_doc.get("product_group")
        plan = {
            "name": plan_doc.name,
            "plan_name": plan_doc.get("plan_name"),
            "product_type": plan_doc.get("product_type"),
            "product_group": plan_doc.get("product_group"),
            "provisioning_module": plan_doc.get("provisioning_module"),
            "server_group": plan_doc.get("server_group"),
        }
    else:
        detail["plan_name"] = plan_name
        detail["product_type"] = None
        detail["product_group"] = None

    server_info = None
    if svc.get("server") and frappe.db.exists("Server", svc.get("server")):
        server_doc = frappe.get_doc("Server", svc.get("server"))
        # Never expose api_secret: Admin Only credential.
        server_info = {
            "hostname": server_doc.get("hostname"),
            "ip_address": server_doc.get("ip_address"),
            "control_panel": server_doc.get("control_panel"),
            "status": server_doc.get("status"),
        }
        detail["server_hostname"] = server_doc.get("hostname")
        detail["server_panel"] = server_doc.get("control_panel")

    invoices = []
    if svc.get("order_ref"):
        invoices = frappe.get_all(
            "Hosting Invoice",
            {"order_ref": svc.order_ref},
            ["name", "status", "total_due", "due_date", "gateway"],
            order_by="creation desc",
        )
    # Payment method: latest invoice gateway (WHMCS billing-info column).
    detail["payment_method"] = (invoices[0].get("gateway") if invoices else None) or None

    # Immutable configuration snapshot + schema labels, secrets stripped.
    schema_fields: list = []
    schema_name = frappe.db.get_value("Hosting Plan", plan_name, "product_type_schema") if plan_name else None
    if schema_name and frappe.db.exists("Product Type Schema", schema_name):
        schema_doc = frappe.get_doc("Product Type Schema", schema_name)
        schema_fields = [f.as_dict() for f in (schema_doc.get("fields") or [])]
    snapshot = _service_snapshot(svc.name, svc.get("order_ref"), plan_name)
    sanitized = _sanitize_snapshot(snapshot, schema_fields)

    # Plan-level defaults (non-secret) for context, e.g. disk/bandwidth rows.
    plan_defaults: list = []
    if plan_name and frappe.db.exists("Hosting Plan", plan_name):
        try:
            plan_doc = plan_doc if "plan_doc" in dir() else frappe.get_doc("Hosting Plan", plan_name)
            for row in plan_doc.get("config_fields") or []:
                key = row.get("field_key")
                if not key or _is_secret_key(key):
                    continue
                if key in snapshot:
                    continue
                if row.get("field_value") in (None, ""):
                    continue
                plan_defaults.append(
                    {"key": key, "label": key.replace("_", " ").title(), "value": row.get("field_value")}
                )
        except Exception:
            plan_defaults = []

    dedicated = frappe.get_all(
        "Dedicated Server Inventory",
        {"assigned_service": svc.name},
        ["name", "asset_id", "location", "status", "cpu", "ram_gb", "ip_pool", "bandwidth_mbps"],
    )
    dedicated_spec = None
    if plan_name and frappe.db.exists("Dedicated Server Configuration", {"hosting_plan": plan_name}):
        spec_name = frappe.db.get_value("Dedicated Server Configuration", {"hosting_plan": plan_name}, "name")
        if spec_name:
            spec = frappe.get_doc("Dedicated Server Configuration", spec_name)
            dedicated_spec = {
                "server_class": spec.get("server_class"),
                "location": spec.get("location"),
                "os_image": spec.get("os_image"),
                "control_panel": spec.get("control_panel"),
                "managed_service": spec.get("managed_service"),
                "ip_count": spec.get("ip_count"),
                "bandwidth_commitment": spec.get("bandwidth_commitment"),
            }
    vps = []
    if svc.get("order_ref"):
        vps = frappe.get_all(
            "VPS Instance",
            {"order_ref": svc.order_ref},
            ["name", "status", "ipv4", "location", "image"],
        )
    vps_spec = None
    if plan_name and frappe.db.exists("VPS Configuration", {"hosting_plan": plan_name}):
        cfg_name = frappe.db.get_value("VPS Configuration", {"hosting_plan": plan_name}, "name")
        if cfg_name:
            cfg = frappe.get_doc("VPS Configuration", cfg_name)
            vps_spec = {
                "cpu_cores": cfg.get("cpu_cores"),
                "ram_mb": cfg.get("ram_mb"),
                "storage_gb": cfg.get("storage_gb"),
                "bandwidth_gb": cfg.get("bandwidth_gb"),
                "ipv4_count": cfg.get("ipv4_count"),
                "backup_enabled": cfg.get("backup_enabled"),
                "disk_overage_rate": cfg.get("disk_overage_rate") or 0,
                "bandwidth_overage_rate": cfg.get("bandwidth_overage_rate") or 0,
            }

    # Server-driven capability flags (ERPNext show_*_button pattern).
    # Frontend renders sections/buttons from these; never guesses.
    from lube_station.lube_station.settings import get_setting

    adapter = _adapter_for_plan(plan_name)
    panel_url = _panel_url_for(svc.get("server"), detail.get("server_panel"))
    is_active = svc.get("status") == "Active"
    can_password = (
        is_active
        and adapter is not None
        and _adapter_overrides(adapter, "change_password")
        and _server_has_api_user(svc.get("server"))
    )
    cancellation_open = bool(get_setting("show_cancellation_link"))
    upgrade_list = _upgrade_options(plan_name, svc.get("billing_cycle")) if is_active else []
    can_vps = bool(vps) and svc.get("status") in ("Active", "Suspended")
    capabilities = {
        "can_vps_control": can_vps,
        "can_vps_rebuild": can_vps,
        "can_vps_rescue": can_vps,
        "can_vps_snapshot": bool(can_vps and (vps_spec or {}).get("backup_enabled")),
        "can_dedicated_control": bool(dedicated) and is_active,
        "can_change_password": can_password,
        "can_sso": _can_sso(svc, adapter),
        "can_panel": bool(panel_url) and is_active,
        "can_upgrade": bool(upgrade_list),
        "can_cancel": bool(cancellation_open and is_active and not svc.get("cancellation_requested")),
    }
    # Resource usage: last 14 snapshots + plan limits (WHMCS bandwidth graphs).
    usage_rows = frappe.get_all(
        "Usage Snapshot",
        {"service_ref": svc.name},
        ["name", "snap_date", "disk_used", "bandwidth_used"],
        order_by="snap_date desc",
        limit=14,
    )
    usage = {
        "snapshots": list(reversed(usage_rows)),
        "limits": {
            "disk": (vps_spec or {}).get("storage_gb") or 0,
            "bandwidth": (vps_spec or {}).get("bandwidth_gb") or 0,
        },
    }
    detail["cancellation_requested"] = bool(svc.get("cancellation_requested"))
    detail["cancellation_mode"] = svc.get("cancellation_mode")
    management = _client_area_for(svc, adapter)
    management_note = (
        "Upgrades swap automatically once the prorated balance is paid "
        "(downgrades with no balance swap immediately). Cancellations need "
        "reason + typed confirmation; Immediate stops now, End of cycle "
        "auto-cancels on next due date and can be withdrawn until then."
    )
    return {
        "service": detail,
        "plan": plan,
        "server": server_info,
        "addons": frappe.get_all(
            "Service",
            {"parent_service": svc.name},
            ["name", "hosting_plan", "status", "billing_cycle", "next_due_date"],
        ),
        "parent_service": svc.get("parent_service"),
        "billing": {
            "billing_cycle": detail.get("billing_cycle"),
            "recurring_amount": detail.get("recurring_amount"),
            "next_due_date": detail.get("next_due_date"),
            "registration_date": detail.get("registration_date"),
            "payment_method": detail.get("payment_method"),
            "order_ref": detail.get("order_ref"),
        },
        "configuration": sanitized["configuration"] + plan_defaults,
        "custom_fields": sanitized["custom_fields"],
        "hidden_count": sanitized["hidden_count"],
        "invoices": invoices,
        "dedicated": dedicated,
        "dedicated_spec": dedicated_spec,
        "vps": vps,
        "vps_spec": vps_spec,
        "capabilities": capabilities,
        "management": management,
        "management_note": management_note,
        "panel_url": panel_url,
        "upgrade_options": upgrade_list,
        "usage": usage,
        "vps_snapshots": _snapshots_for([v.get("name") for v in vps]),
    }


def _service_for_customer(service: str):
    """Owned service or PermissionError (Helpdesk per-ticket guard pattern)."""
    svc = frappe.get_doc("Service", service)
    assert_owns(svc.customer)
    return svc


def _check_password_strength(password: str):
    if len(password or "") < 10:
        frappe.throw("Password needs 10+ characters")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        frappe.throw("Password needs both letters and numbers")


@frappe.whitelist(methods=["POST"])
def change_service_password(service: str, new_password: str) -> dict:
    """WHMCS Change Password: Active services only, module must implement it.

    Synchronous like vps_control; the plaintext password is passed to the
    adapter call and never stored, logged, or returned.
    """
    svc = _service_for_customer(service)
    if svc.get("status") != "Active":
        frappe.throw("Password change is available for Active services only")
    _check_password_strength(new_password or "")
    adapter = _adapter_for_plan(svc.get("hosting_plan"))
    if adapter is None or not _adapter_overrides(adapter, "change_password"):
        frappe.throw("Password change is not supported for this product")
    if not _server_has_api_user(svc.get("server")):
        frappe.throw("Password change is not available for this service yet")
    try:
        adapter.change_password(service, new_password)
    except frappe.ValidationError:
        raise
    except Exception:
        frappe.throw("Password change failed, please try again later")
    try:
        svc.add_comment("Comment", "Service password changed via customer portal.")
    except Exception:
        pass
    return {"changed": True}


@frappe.whitelist(methods=["POST"])
def get_panel_login(service: str) -> dict:
    """Single-click hosting panel login: short-lived one-time URL.

    Owner-only, Active services only, rate-limited. Adapter creates the
    session with server-side API creds; the URL (with token) is returned
    to the owner only and never stored or logged.
    """
    if not isinstance(service, str) or not service.strip():
        frappe.throw("Service is required")
    svc = _service_for_customer(service.strip())
    if svc.get("status") != "Active":
        frappe.throw("Panel login is available for Active services only")
    if not _sso_rate_ok(svc.name):
        frappe.throw("Rate limit exceeded, try later")
    adapter = _adapter_for_plan(svc.get("hosting_plan"))
    if adapter is None or not _adapter_overrides(adapter, "create_sso_session"):
        frappe.throw("Panel login is not supported for this product")
    if not _server_has_api_user(svc.get("server")):
        frappe.throw("Panel login is not available for this service yet")
    try:
        out = adapter.create_sso_session(svc.name)
    except frappe.ValidationError:
        raise
    except Exception:
        frappe.throw("Panel login failed, please try again later")
    url = (out.get("url") or "").strip() if isinstance(out, dict) else ""
    if not url.startswith("https://"):
        frappe.throw("Panel login failed, please try again later")
    try:
        svc.add_comment("Comment", "Panel login issued via customer portal.")
    except Exception:
        pass
    return {"url": url, "expires_in": 60}


@frappe.whitelist(methods=["POST"])
def request_cancellation(
    service: str, reason: str, mode: str = "End of Billing Cycle", confirm_text: str | None = None, acknowledged: bool = False
) -> dict:
    """Guarded automatic cancellation.

    Safeguards against accidental clicks (frontend also enforces):
    reason >= 10 chars, mode radio, type-service-ID to confirm, explicit
    acknowledge checkbox. Immediate terminates now; End of Billing Cycle
    stays Active until next due date (daily scheduler auto-terminates).
    Withdraw via withdraw_cancellation while still Active.
    """
    from lube_station.lube_station.settings import get_setting

    svc = _service_for_customer(service)
    if not get_setting("show_cancellation_link"):
        frappe.throw("Cancellation requests are disabled")
    if svc.get("status") != "Active":
        frappe.throw("Cancellation can be requested for Active services only")
    if svc.get("cancellation_requested"):
        frappe.throw("A cancellation request is already open for this service")
    reason = (reason or "").strip()
    if len(reason) < 10:
        frappe.throw("Please tell us why (10+ characters) so we can help")
    if mode not in ("Immediate", "End of Billing Cycle"):
        frappe.throw("Unknown cancellation mode")
    if (confirm_text or "").strip() != svc.name:
        frappe.throw(f"Type {svc.name} to confirm cancellation")
    if not acknowledged or str(acknowledged).lower() not in ("1", "true"):
        frappe.throw("Please acknowledge you understand the cancellation")
    svc.cancellation_requested = 1
    svc.cancellation_mode = mode
    svc.cancellation_reason = reason
    svc.save(ignore_permissions=True)
    if mode == "Immediate":
        try:
            svc.reload()
            svc.terminate(f"Auto-cancel via portal (Immediate): {reason}")
        except Exception as e:
            frappe.throw(f"Cancellation failed: {e}")
        return {"requested": True, "mode": mode, "terminated": True}
    try:
        svc.add_comment("Comment", f"Cancellation scheduled via portal ({mode}): {reason}")
    except Exception:
        pass
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        notify_customer(svc.get("customer"), "cancellation_request", f"{service}:cancel", {"service": service, "mode": mode, "reason": reason})
    except Exception:
        pass
    return {"requested": True, "mode": mode, "terminated": False}


@frappe.whitelist(methods=["POST"])
def withdraw_cancellation(service: str) -> dict:
    """Undo a scheduled (not yet executed) cancellation."""
    svc = _service_for_customer(service)
    if not svc.get("cancellation_requested"):
        frappe.throw("No open cancellation request for this service")
    if svc.get("status") != "Active":
        frappe.throw("Only scheduled cancellations on Active services can be withdrawn")
    svc.cancellation_requested = 0
    svc.cancellation_mode = None
    svc.cancellation_reason = None
    svc.save(ignore_permissions=True)
    try:
        svc.add_comment("Comment", "Cancellation withdrawn via portal.")
    except Exception:
        pass
    return {"withdrawn": True}


def process_scheduled_cancellations() -> dict:
    """Daily: auto-terminate end-of-cycle requests past next due date."""
    from frappe.utils import getdate, today

    rows = frappe.get_all(
        "Service",
        {"cancellation_requested": 1, "cancellation_mode": "End of Billing Cycle", "status": "Active"},
        ["name", "next_due_date", "cancellation_reason"],
    )
    done = []
    for r in rows:
        try:
            if r.get("next_due_date") and getdate(r["next_due_date"]) > getdate(today()):
                continue
            doc = frappe.get_doc("Service", r.name)
            doc.terminate(f"Auto-cancel via portal (end of cycle): {r.get('cancellation_reason') or ''}")
            done.append(r.name)
        except Exception:
            continue
    return {"terminated": done}


@frappe.whitelist(methods=["GET"])
def upgrade_options(service: str) -> list:
    """Upgrade/downgrade targets: same product type, priced for the cycle."""
    svc = _service_for_customer(service)
    return _upgrade_options(svc.get("hosting_plan"), svc.get("billing_cycle"))


@frappe.whitelist(methods=["GET"])
def upgrade_quote(service: str, new_plan: str) -> dict:
    """Price breakdown before confirm (old/new/prorated/setup/total)."""
    svc = _service_for_customer(service)
    if svc.get("status") != "Active":
        frappe.throw("Upgrades apply to Active services only")
    options = {o["plan"]: o for o in _upgrade_options(svc.get("hosting_plan"), svc.get("billing_cycle"))}
    if new_plan not in options:
        frappe.throw("That plan is not an upgrade option for this service")
    return _upgrade_quote(svc, new_plan)


@frappe.whitelist(methods=["POST"])
def request_upgrade(service: str, new_plan: str) -> dict:
    """Automatic upgrade/downgrade.

    Positive prorated balance -> Accepted order + Unpaid invoice; the plan
    swaps automatically in on_invoice_paid once the invoice is Paid.
    Zero/negative balance -> immediate swap + Credit Note for the negative part.
    Idempotent on retry via upgrade:{service}:{new_plan} invoice key.
    """
    from frappe.utils import add_days, today

    from lube_station.lube_station.settings import get_setting

    svc = _service_for_customer(service)
    if svc.get("status") != "Active":
        frappe.throw("Upgrades apply to Active services only")
    options = {o["plan"]: o for o in _upgrade_options(svc.get("hosting_plan"), svc.get("billing_cycle"))}
    if new_plan not in options:
        frappe.throw("That plan is not an upgrade option for this service")
    quote = _upgrade_quote(svc, new_plan)
    key = f"upgrade:{service}:{new_plan}"
    if frappe.db.exists("Hosting Invoice", {"idempotency_key": key}):
        inv = frappe.get_doc("Hosting Invoice", {"idempotency_key": key})
        if inv.status == "Paid":
            _apply_plan_swap(service, new_plan, invoice_name=inv.name)
            return {"order": inv.order_ref, "invoice": inv.name, "status": "Paid", "applied": True, "quote": quote}
        try:
            from lube_station.lube_station.payments.links import payment_link

            pay = payment_link(inv.name, None)
        except Exception:
            pay = {}
        return {
            "order": inv.order_ref,
            "invoice": inv.name,
            "status": inv.status,
            "total_due": inv.total_due,
            "payment_required": True,
            "payment": pay,
            "quote": quote,
        }
    if quote["total_due"] <= 0:
        credit = round(-quote["total_due"], 2) if quote["total_due"] < 0 else 0
        out = _apply_plan_swap(service, new_plan, credit_amount=credit)
        return {"order": None, "invoice": None, "applied": True, "credit_note": out.get("credit_note"), "quote": quote}
    order = frappe.get_doc(
        {
            "doctype": "Order",
            "customer": svc.get("customer"),
            "status": "Accepted",
            "customer_notes": f"Portal upgrade: {svc.name} from {svc.get('hosting_plan')} to {new_plan} (prorated {quote['total_due']})",
            "items": [
                {
                    "item_type": "Hosting Plan",
                    "reference": new_plan,
                    "billing_cycle": svc.get("billing_cycle"),
                    "unit_price": quote["total_due"],
                    "quantity": 1,
                    "configuration_snapshot": json.dumps(
                        {"upgrade_of": svc.name, "upgrade_to": new_plan, "prorated": quote["total_due"]}
                    ),
                }
            ],
        }
    ).insert(ignore_permissions=True)
    # Single-line upgrade invoice (tax + credit like initial invoices).
    taxable = True
    if frappe.db.exists("Hosting Plan", new_plan):
        flag = frappe.db.get_value("Hosting Plan", new_plan, "taxable")
        taxable = True if flag is None else bool(flag)
    tax = 0
    subtotal = quote["total_due"]
    label = "No tax"
    breakup = {"cgst": 0, "sgst": 0, "ugst": 0, "igst": 0}
    if frappe.db.exists("DocType", "Tax Rule"):
        from lube_station.lube_billing.doctype.tax_rule.tax_rule import tax_breakup

        out = tax_breakup(svc.get("customer"), [{"amount": quote["total_due"], "taxable": taxable}])
        tax = out["total"]
        label = out["label"]
        breakup = out
        if out["mode"] == "inclusive":
            subtotal = round(quote["total_due"] - tax, 2)
    credit = 0
    if frappe.db.exists("DocType", "Credit Note"):
        from lube_station.lube_customers.doctype.credit_note.credit_note import apply_credit

        credit = apply_credit(svc.get("customer"), quote["total_due"] + tax)
    inv = frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": svc.get("customer"),
            "order_ref": order.name,
            "invoice_items": [
                {
                    "description": f"Upgrade {service}: {quote['old_plan']} -> {new_plan} ({quote['remaining_days']}/{quote['cycle_days']} days)",
                    "service_ref": new_plan,
                    "amount": quote["total_due"],
                }
            ],
            "tax_amount": tax,
            "subtotal_amount": subtotal,
            "tax_label": label,
            "cgst_amount": breakup["cgst"],
            "sgst_amount": breakup["sgst"],
            "ugst_amount": breakup["ugst"],
            "igst_amount": breakup["igst"],
            "credit_applied": credit,
            "due_date": add_days(today(), get_setting("invoice_due_days") or 7),
            "status": "Unpaid",
            "idempotency_key": key,
        }
    ).insert(ignore_permissions=True)
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        notify_customer(svc.get("customer"), "invoice", inv.name, {"invoice": inv.name, "amount": inv.total_due})
        notify_customer(
            svc.get("customer"), "upgrade", f"{service}:{order.name}", {"service": service, "from": svc.get("hosting_plan"), "to": new_plan, "order": order.name}
        )
    except Exception:
        pass
    try:
        svc.add_comment("Comment", f"Upgrade invoice {inv.name} for {new_plan} (order {order.name}). Plan swaps on payment.")
    except Exception:
        pass
    try:
        from lube_station.lube_station.payments.links import payment_link

        pay = payment_link(inv.name, None)
    except Exception:
        pay = {}
    return {
        "order": order.name,
        "status": order.status,
        "invoice": inv.name,
        "total_due": inv.total_due,
        "payment_required": True,
        "payment": pay,
        "quote": quote,
    }


@frappe.whitelist(methods=["GET"])
def my_domains():
    customer = my_customer()
    return frappe.get_all("Registered Domain", {"customer": customer}, ["domain_name", "status", "expiry_date"])


@frappe.whitelist(methods=["GET"])
def dns_list(domain: str):
    dom = frappe.get_doc("Registered Domain", domain)
    assert_owns(dom.customer)
    return frappe.get_all("DNS Record", {"domain": domain}, ["name", "record_type", "hostname", "record_value", "ttl"])


@frappe.whitelist(methods=["POST"])
def vps_control(instance: str, action: str, arg: str | None = None):
    from lube_station.lube_provisioning.doctype.vps_instance.vps_instance import vps_action

    inst = frappe.get_doc("VPS Instance", instance)
    if inst.order_ref:
        order = frappe.get_doc("Order", inst.order_ref)
        if order.customer:
            assert_owns(order.customer)
    out = vps_action(instance, action, arg)
    if action == "snapshot":
        # Registry row so customers can pick a restore point later.
        # Provider id lands here when live; sandbox stores a local key.
        try:
            label = (arg or "").strip() or None
            frappe.get_doc(
                {
                    "doctype": "VPS Snapshot",
                    "instance": instance,
                    "snapshot_ref": f"{instance}-{frappe.generate_hash(length=10)}",
                    "label": label,
                    "status": "Available",
                }
            ).insert(ignore_permissions=True)
        except Exception:
            pass
    return out


def _snapshots_for(instances: list) -> list:
    if not instances:
        return []
    return frappe.get_all(
        "VPS Snapshot",
        {"instance": ["in", instances], "status": ["!=", "Deleted"]},
        ["name", "instance", "snapshot_ref", "label", "status", "creation"],
        order_by="creation desc",
    )


def _owns_vps_instance(instance: str):
    inst = frappe.get_doc("VPS Instance", instance)
    if inst.order_ref:
        order = frappe.get_doc("Order", inst.order_ref)
        if order.customer:
            assert_owns(order.customer)
    return inst


@frappe.whitelist(methods=["GET"])
def vps_snapshots(instance: str) -> list:
    """Restore points for an owned instance, newest first."""
    _owns_vps_instance(instance)
    return frappe.get_all(
        "VPS Snapshot",
        {"instance": instance, "status": ["!=", "Deleted"]},
        ["name", "snapshot_ref", "label", "status", "creation"],
        order_by="creation desc",
    )


@frappe.whitelist(methods=["POST"])
def vps_restore(instance: str, snapshot: str) -> dict:
    """Restore an owned instance to one of its snapshots.

    Active services only (destructive). Audit-logged via vps_action;
    provider executes when live creds land (manual gate).
    """
    from lube_station.lube_provisioning.doctype.vps_instance.vps_instance import vps_action

    inst = _owns_vps_instance(instance)
    snap = frappe.get_doc("VPS Snapshot", snapshot)
    if snap.get("instance") != instance:
        frappe.throw("Snapshot does not belong to this instance")
    if snap.get("status") == "Deleted":
        frappe.throw("Snapshot is no longer available")
    if inst.get("status") != "Active":
        frappe.throw("Restore is available for Active instances only")
    out = vps_action(instance, "restore", snap.get("snapshot_ref"))
    try:
        snap.status = "Restoring"
        snap.save(ignore_permissions=True)
        svc_names = frappe.get_all("Service", {"order_ref": inst.order_ref}, pluck="name") if inst.order_ref else []
        for svc_name in svc_names:
            try:
                frappe.get_doc("Service", svc_name).add_comment(
                    "Comment", f"Snapshot restore requested via portal ({snap.name})."
                )
            except Exception:
                continue
    except Exception:
        pass
    return {**out, "snapshot": snap.name}


def _owns_dedicated(inventory: str):
    """Dedicated row assigned to an owned service, or PermissionError."""
    inv = frappe.get_doc("Dedicated Server Inventory", inventory)
    if not inv.get("assigned_service") or not frappe.db.exists("Service", inv.get("assigned_service")):
        frappe.throw("Server is not assigned to a service", frappe.PermissionError)
    svc = frappe.get_doc("Service", inv.get("assigned_service"))
    assert_owns(svc.customer)
    return inv, svc


# Portal-safe dedicated steps. "credentials" stays Admin Only (portal-vault).
_PORTAL_DEDICATED_STEPS = ("install_os", "rescue", "network", "rdns", "panel", "monitoring")


@frappe.whitelist(methods=["POST"])
def dedicated_control(inventory: str, step: str, arg: str | None = None):
    """WHMCS dedicated controls: reinstall, network, rDNS, panel, monitoring.

    Mirrors vps_control: ownership-checked, audit-logged, queued for the
    provider. No live effect until provider creds land (manual gate).
    """
    import re

    from lube_station.lube_station.provisioning.dedicated import provision_step

    inv, svc = _owns_dedicated(inventory)
    if step not in _PORTAL_DEDICATED_STEPS:
        frappe.throw("Unknown step")
    if svc.get("status") != "Active":
        frappe.throw("Server controls are available for Active services only")
    if step == "rdns":
        hostname = (arg or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9]([a-z0-9.-]{0,251}[a-z0-9])?", hostname) or "." not in hostname:
            frappe.throw("Enter a valid hostname for rDNS")
        out = provision_step(inventory, step)
        try:
            svc.add_comment("Comment", f"rDNS requested via portal for {inv.name}: {hostname}.")
        except Exception:
            pass
        return {**out, "hostname": hostname}
    return provision_step(inventory, step)


@frappe.whitelist(methods=["GET"])
def my_methods():
    customer = my_customer()
    return frappe.get_all("Saved Payment Method", {"customer": customer}, ["name", "gateway", "last_four", "expiry", "default_method"])


@frappe.whitelist(methods=["POST"])
def save_method(gateway: str, token: str, last_four: str | None = None, expiry: str | None = None, make_default: bool = False):
    customer = my_customer()
    doc = frappe.get_doc({"doctype": "Saved Payment Method", "customer": customer, "gateway": gateway, "token": token, "last_four": last_four, "expiry": expiry, "default_method": 1 if make_default else 0}).insert()
    return {"method": doc.name}


@frappe.whitelist(methods=["GET"])
def my_dedicated():
    customer = my_customer()
    services = frappe.get_all("Service", {"customer": customer}, pluck="name")
    if not services:
        return []
    return frappe.get_all("Dedicated Server Inventory", {"assigned_service": ["in", services]}, ["name", "asset_id", "location", "status", "assigned_service"])


@frappe.whitelist(methods=["POST"])
def dns_add(domain: str, record_type: str, hostname: str, value: str, ttl: int = 3600):
    dom = frappe.get_doc("Registered Domain", domain)
    assert_owns(dom.customer)
    rec = frappe.get_doc({"doctype": "DNS Record", "domain": domain, "record_type": record_type, "hostname": hostname, "record_value": value, "ttl": ttl}).insert()
    return {"record": rec.name}


@frappe.whitelist(methods=["GET"])
def downloads():
    from lube_station.lube_catalog.doctype.downloadable_asset.downloadable_asset import check_entitlement

    assets = frappe.get_all("Downloadable Asset", {"active": 1}, ["name", "title", "access_policy"])
    return [a for a in assets if check_entitlement(a.name)["allowed"]]


@frappe.whitelist(methods=["GET"])
def my_account():
    customer = my_customer()
    return frappe.get_doc("Hosting Customer", customer).as_dict()


@frappe.whitelist(methods=["GET", "POST"])
def cart_current():
    """Get open cart for logged-in customer, creating one if needed.

    Customer cycle: storefront (guest) -> signup/login -> cart_current ->
    cart_add -> checkout -> pay -> my_services.
    """
    customer = my_customer()
    cart_doc = _open_cart(customer)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["POST"])
def cart_add(hosting_plan: str, billing_cycle: str = "Monthly", quantity: int = 1, domain: str | None = None, configuration: dict | str | None = None, cart: str | None = None, parent_service: str | None = None):
    import json

    customer = my_customer()
    cart_doc = frappe.get_doc("Cart", cart) if cart else _open_cart(customer)
    _assert_cart_access(cart_doc)
    if not cart_doc.customer:
        cart_doc.customer = customer
    if not frappe.db.exists("Hosting Plan", hosting_plan):
        frappe.throw(f"Unknown plan {hosting_plan}")
    if not frappe.db.get_value("Hosting Plan", hosting_plan, "is_active"):
        frappe.throw(f"Plan {hosting_plan} is not active")
    if parent_service:
        if not frappe.db.exists("Service", parent_service):
            frappe.throw(f"Unknown service {parent_service}")
        parent = frappe.get_doc("Service", parent_service)
        assert_owns(parent.customer)
        if parent.customer != customer:
            frappe.throw("Add-on parent belongs to another customer", frappe.PermissionError)
        if parent.status in ("Terminated", "Cancelled"):
            frappe.throw("Cannot attach an add-on to a closed service")
    if isinstance(configuration, dict):
        configuration = json.dumps(configuration)
    try:
        parsed_config = json.loads(configuration or "{}") if isinstance(configuration, str) else dict(configuration or {})
    except Exception:
        parsed_config = {}
    schema = frappe.db.get_value("Hosting Plan", hosting_plan, "product_type_schema")
    if schema:
        from lube_station.lube_catalog.doctype.product_type_schema.product_type_schema import validate_config

        # Domain is picked in step 2 (Domain.vue); enforced at place_order.
        validate_config(schema, parsed_config, domain=domain, enforce_domain=False)
    cart_doc.append(
        "items",
        {
            "item_type": "Hosting Plan",
            "hosting_plan": hosting_plan,
            "billing_cycle": billing_cycle,
            "domain": domain,
            "parent_service": parent_service,
            "quantity": quantity or 1,
            "configuration_json": configuration,
        },
    )
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["GET", "POST"], allow_guest=True)
def domain_check(domain: str) -> dict:
    """Guest-safe availability lookup (rate-limited server-side)."""
    from lube_station.lube_domains.doctype.registered_domain.registered_domain import check_availability

    return check_availability(domain)


def _premium_for(domain: str, domain_action: str) -> float:
    """Registrar premium price for a register action, else 0.

    Money-safe: premium domains must bill the registrar price, never the
    TLD rate. Uses the cached availability lookup (no extra registrar hit
    in the normal Domain.vue-first flow).
    """
    if domain_action != "register":
        return 0
    from lube_station.lube_domains.doctype.registered_domain.registered_domain import check_availability

    out = check_availability((domain or "").strip().lower())
    if out.get("status") == "Premium":
        premium = out.get("premium_price") or 0
        if not premium:
            frappe.throw("Premium price unavailable right now, try again later")
        return premium
    return 0


@frappe.whitelist(methods=["GET", "POST"], allow_guest=True)
def subdomain_suffixes() -> list:
    """Offered free-subdomain suffixes (guest-safe: seller-published config)."""
    from lube_station.lube_domains.doctype.registered_domain.registered_domain import subdomain_suffixes as _suffixes

    return _suffixes()


@frappe.whitelist(methods=["POST"])
def cart_add_domain(cart: str, domain: str, domain_action: str = "register", years: int = 1, auth_code: str | None = None):
    """Domain-only line (register/transfer). WHMCS domain step without hosting."""
    import json

    cart_doc = frappe.get_doc("Cart", cart)
    _assert_cart_access(cart_doc)
    if domain_action == "subdomain":
        frappe.throw("Free subdomains attach to a hosting plan, pick one first")
    _validate_domain_choice(domain, domain_action, auth_code)
    premium = _premium_for(domain, domain_action)
    if premium and (years or 1) != 1:
        frappe.throw("Premium domains register for 1 year; renew after at the regular rate")
    cart_doc.append(
        "items",
        {
            "item_type": "Domain",
            "domain": domain.strip().lower(),
            "billing_cycle": "One Time",
            "quantity": years or 1,
            "configuration_json": json.dumps({"domain_action": domain_action, "domain_years": years or 1, "epp": auth_code or "", "premium_price": premium or None}),
        },
    )
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["POST"])
def cart_set_domain(cart: str, row: str, domain: str | None = None, domain_action: str = "none", years: int = 1, auth_code: str | None = None):
    """Attach WHMCS domain choice to a hosting-plan cart row.

    domain_action: register | transfer | own | subdomain | none.
    """
    import json

    from lube_station.lube_domains.doctype.registered_domain.registered_domain import validate_subdomain

    cart_doc = frappe.get_doc("Cart", cart)
    _assert_cart_access(cart_doc)
    if domain_action == "subdomain":
        domain = validate_subdomain(domain)
    elif domain_action != "none":
        _validate_domain_choice(domain, domain_action, auth_code)
        if _premium_for(domain, domain_action):
            frappe.throw("That is a premium domain: order it as a separate domain item")
    item = _cart_row(cart_doc, row)
    item.domain = (domain or "").strip().lower() or None
    config = {}
    try:
        config = json.loads(item.configuration_json or "{}")
    except Exception:
        config = {}
    config.update({"domain_action": domain_action, "domain_years": years or 1, "epp": auth_code or ""})
    item.configuration_json = json.dumps(config)
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


def _validate_domain_choice(domain: str | None, domain_action: str, auth_code: str | None):
    if domain_action not in ("register", "transfer", "own", "none"):
        frappe.throw("Unknown domain option")
    if domain_action == "none":
        return
    domain = (domain or "").strip().lower()
    if not domain or "." not in domain:
        frappe.throw("Enter a valid domain name")
    if domain_action == "transfer" and not (auth_code or "").strip():
        frappe.throw("Transfer needs the EPP authorization code")


@frappe.whitelist(methods=["POST"])
def cart_set_qty(cart: str, row: str, quantity: int):
    cart_doc = frappe.get_doc("Cart", cart)
    _assert_cart_access(cart_doc)
    quantity = frappe.utils.cint(quantity)
    if quantity < 1:
        frappe.throw("Quantity must be at least 1")
    _cart_row(cart_doc, row).quantity = quantity
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["POST"])
def cart_remove(cart: str, row: str):
    cart_doc = frappe.get_doc("Cart", cart)
    _assert_cart_access(cart_doc)
    _cart_row(cart_doc, row)
    cart_doc.items = [i for i in cart_doc.items if i.name != row]
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["POST"])
def cart_apply_coupon(cart: str, coupon_code: str):
    from lube_station.lube_customers.doctype.cart.cart import discount_for  # noqa: F401

    cart_doc = frappe.get_doc("Cart", cart)
    _assert_cart_access(cart_doc)
    code = (coupon_code or "").strip()
    coupon_name = frappe.db.get_value("Coupon", {"code": code}, "name")
    if not coupon_name:
        frappe.throw("This coupon code is not valid.")
    coupon = frappe.get_doc("Coupon", coupon_name)
    coupon.check_cart(cart_doc)
    cart_doc.coupon_code = coupon.code
    cart_doc.save(ignore_permissions=True)
    return _cart_view(cart_doc)


@frappe.whitelist(methods=["GET", "POST"])
def payment_gateways() -> list:
    """Enabled gateways with a real bridge behind them, in Settings order.

    PayPal Checkout stays hidden: classic NVP API has no INR support and
    Hosting Invoices are INR-only. Re-add when invoice currency lands.
    """
    from lube_station.lube_station.payments.links import gateway_order

    rows = frappe.get_all("Payment Gateway Adapter", {"active": 1, "supports_one_time": 1}, ["name"])
    names = {r.name for r in rows}
    return [{"name": g} for g in gateway_order() if g in names]


@frappe.whitelist(methods=["POST"])
def checkout(cart: str | None = None, gateway: str | None = None, notes: str | None = None, tos_accepted: bool = False) -> dict:
    """One-call purchase: cart -> Order -> Hosting Invoice -> payment link.

    WHMCS Complete Order: ownership + TOS enforced, fraud scored in
    place_order, order/invoice notifications fired, idempotent on retry.
    """
    from lube_station.lube_billing.doctype.hosting_invoice.hosting_invoice import generate_invoice
    from lube_station.lube_customers.doctype.order.order import place_order
    from lube_station.lube_station.notifications.events import fire
    from lube_station.lube_station.payments.links import payment_link, pick_gateway

    customer = my_customer()
    from lube_station.lube_station.settings import get_setting

    if get_setting("tos_required") and not _is_staff() and not frappe.db.get_value("Hosting Customer", customer, "tos_accepted"):
        if not tos_accepted:
            frappe.throw("Accept the Terms of Service to check out")
        frappe.db.set_value("Hosting Customer", customer, "tos_accepted", 1)
    cart_doc = frappe.get_doc("Cart", cart) if cart else _open_cart(customer)
    _assert_cart_access(cart_doc)
    if not cart_doc.items:
        frappe.throw("Cart empty")
    # Fail fast on bad gateway before creating order/invoice side effects.
    pick_gateway(gateway or cart_doc.get("gateway") or None)
    if not cart_doc.customer:
        cart_doc.customer = customer
        cart_doc.save(ignore_permissions=True)
    if frappe.db.exists("Order", {"source_cart": cart_doc.name}):
        order_name = frappe.db.get_value("Order", {"source_cart": cart_doc.name}, "name")
    else:
        order_name = place_order(cart_doc.name, customer, notes)["order"]
        _notify(customer, fire, "order", order_name)
    inv = generate_invoice(order_name, gateway)
    # Invoice mail already fired once inside generate_invoice (_notify_invoice);
    # re-firing here would only hit the Notification Event dedupe, so skip it.
    link = payment_link(inv["invoice"], gateway)
    return {"order": order_name, "customer": customer, **inv, "payment": link}


def _notify(customer: str, fire, event_type: str, reference: str):
    try:
        user = frappe.db.get_value("Hosting Customer", customer, "user")
        email = frappe.db.get_value("User", user, "email") if user else None
        fire(event_type, reference, email)
    except Exception:
        pass


@frappe.whitelist(methods=["GET"])
def my_orders():
    customer = my_customer()
    return frappe.get_all("Order", {"customer": customer}, ["name", "status", "total", "creation"], order_by="creation desc")


@frappe.whitelist(methods=["GET"])
def my_order_detail(order: str):
    order_doc = frappe.get_doc("Order", order)
    assert_owns(order_doc.customer)
    invoices = frappe.get_all("Hosting Invoice", {"order_ref": order}, ["name", "status", "total_due", "gateway"])
    return {
        "order": order_doc.as_dict(),
        "invoices": invoices,
    }


@frappe.whitelist(methods=["GET", "POST"])
def invoice_payment_link(invoice: str, gateway: str | None = None):
    from lube_station.lube_station.payments.links import payment_link

    inv = frappe.get_doc("Hosting Invoice", invoice)
    assert_owns(inv.customer)
    return payment_link(invoice, gateway)


@frappe.whitelist(methods=["POST"])
def invoice_pay_saved(invoice: str, payment_method: str):
    from lube_station.lube_station.payments.methods import charge_saved_method

    inv = frappe.get_doc("Hosting Invoice", invoice)
    assert_owns(inv.customer)
    method = frappe.get_doc("Saved Payment Method", payment_method)
    assert_owns(method.customer)
    return charge_saved_method(payment_method, invoice)


@frappe.whitelist(methods=["POST"], allow_guest=True)
def signup_customer(
    full_name: str,
    email: str,
    password: str,
    company: str | None = None,
    phone: str | None = None,
    address_line1: str | None = None,
    city: str | None = None,
    state: str | None = None,
    postcode: str | None = None,
    country: str | None = None,
    tos_accepted: bool = False,
) -> dict:
    import re

    email = (email or "").strip().lower()
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        frappe.throw("Invalid email")
    if len(password or "") < 8:
        frappe.throw("Password needs 8+ characters")
    if not (full_name or "").strip():
        frappe.throw("Full name required")
    if not tos_accepted:
        frappe.throw("Accept the Terms of Service to register")
    if frappe.db.exists("User", email):
        frappe.throw("Account already exists, sign in instead")
    from lube_station.lube_billing.doctype.tax_rule.tax_rule import normalize_country

    country = normalize_country(country) or None
    if country and not frappe.db.exists("Country", country):
        frappe.throw("Select a valid country")
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": full_name, "enabled": 1, "new_password": password, "roles": [{"role": "Customer"}]}).insert(ignore_permissions=True)
    customer = frappe.get_doc(
        {
            "doctype": "Hosting Customer",
            "user": user.name,
            "company": company,
            "phone": phone,
            "address_line1": address_line1,
            "city": city,
            "state": state,
            "postcode": postcode,
            "country": country,
            "tos_accepted": 1,
            "status": "Active",
        }
    ).insert(ignore_permissions=True)
    try:
        from lube_station.lube_station.notifications.events import fire

        fire("signup", customer.name, email)
    except Exception:
        pass
    return {"customer": customer.name}


@frappe.whitelist(methods=["GET", "POST"], allow_guest=True)
def country_list() -> list:
    """All countries for the signup dropdown (uses the Country master)."""
    if not frappe.db.exists("DocType", "Country"):
        return [{"name": "India", "code": "IN"}]
    return [
        {"name": c.name, "code": (c.code or "").upper()}
        for c in frappe.get_all("Country", ["name", "code"], order_by="name")
    ]


@frappe.whitelist(methods=["GET", "POST"], allow_guest=True)
def pincode_lookup(postcode: str, country: str | None = None) -> dict:
    """City/state autofill from postal code (free public APIs, no keys).

    India (6-digit PIN): api.postalpincode.in. Everywhere else:
    zippopotam.us via the Country master's ISO code. Never blocks signup:
    failures throw a message telling the customer to type manually.
    """
    import re

    from frappe.integrations.utils import make_get_request

    code = (postcode or "").strip().replace(" ", "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 \-]{2,9}", code or ""):
        frappe.throw("Enter a valid postcode")
    country_name = (country or "").strip()

    def indian() -> bool:
        if country_name.lower() in ("india", "bharat"):
            return True
        return not country_name and bool(re.fullmatch(r"\d{6}", code))

    # NOTE: these free APIs reset connections presenting the default
    # python-requests UA — a browser UA is required from bench Python.
    _UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"}
    try:
        if indian():
            if not re.fullmatch(r"\d{6}", code):
                frappe.throw("Indian PIN is 6 digits")
            resp = make_get_request(f"https://api.postalpincode.in/pincode/{code}", headers=_UA)
            offices = (resp[0].get("PostOffice") if isinstance(resp, list) and resp else None) or []
            if (resp[0].get("Status") if resp else "") != "Success" or not offices:
                frappe.throw("No record for this PIN, enter city manually")
            office = offices[0]
            return {"city": office.get("District") or office.get("Name"), "state": office.get("State"), "country": "India"}
        iso = frappe.db.get_value("Country", country_name, "code") if country_name else None
        if not iso:
            frappe.throw("Pick a country first, or enter city manually")
        resp = make_get_request(f"https://api.zippopotam.us/{iso.lower()}/{code}", headers=_UA)
        places = resp.get("places") or []
        if not places:
            frappe.throw("No record for this postcode, enter city manually")
        return {"city": places[0].get("place name"), "state": places[0].get("state"), "country": country_name}
    except frappe.ValidationError:
        raise
    except Exception:
        frappe.throw("Lookup unavailable right now, enter city manually")


@frappe.whitelist(methods=["POST"], allow_guest=True)
def forgot_password(email: str) -> dict:
    from frappe.core.doctype.user.user import reset_password

    clean = email.strip().lower()
    reset_password(clean)
    try:
        from lube_station.lube_station.notifications.events import fire

        # Core already sent reset link; audit only, no duplicate mail.
        fire("password_reset", clean, clean, send_mail=False)
    except Exception:
        pass
    return {"sent": True}
