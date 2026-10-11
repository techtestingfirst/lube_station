import frappe
from frappe.model.document import Document
from frappe.utils import add_days, today

CYCLE_MONTHS = {
    "Monthly": 1,
    "Quarterly": 3,
    "Semi-Annually": 6,
    "Annually": 12,
    "Biennially": 24,
    "Triennially": 36,
}

STATUS_COLORS = {
    "Paid": "#16a34a",
    "Unpaid": "#d97706",
    "Overdue": "#dc2626",
    "Cancelled": "#6b7280",
    "Draft": "#6b7280",
}


class HostingInvoice(Document):
    def validate(self):
        items_total = sum(i.amount or 0 for i in self.invoice_items)
        subtotal = self.subtotal_amount if self.subtotal_amount else items_total
        self.total_due = max(subtotal + (self.tax_amount or 0) - (self.credit_applied or 0), 0)

    def on_update(self):
        try:
            before = self.get_doc_before_save()
        except Exception:
            before = None
        if before and before.status != "Paid" and self.status == "Paid":
            # Wallet reservation settles exactly once, however Paid arrived
            # (gateway callback, Desk edit, verification poll).
            try:
                from lube_station.lube_customers.doctype.credit_note.credit_note import consume_credit

                consume_credit(self.name)
            except Exception as e:
                frappe.log_error(f"Wallet consume failed for {self.name}: {e}")

    def on_payment_authorized(self, payment_status):
        """Called by Payments app (Razorpay/Stripe) after checkout completes.

        Marks invoice Paid, records the gateway payment, activates services.
        Idempotent: repeat callbacks reuse existing transaction.
        """
        if payment_status not in ("Authorized", "Verified", "Completed"):
            return
        if self.status == "Paid":
            return "/store/invoices"
        data = (frappe.flags.data or {}) if hasattr(frappe.flags, "data") else {}
        gateway_txn = str(data.get("razorpay_payment_id") or data.get("stripe_token_id") or data.get("transaction_id") or "")
        if data.get("stripe_token_id"):
            gateway = "Stripe"
        elif data.get("razorpay_payment_id"):
            gateway = "Razorpay"
        else:
            gateway = "PayPal"
            if not gateway_txn:
                gateway_txn = _paypal_txn_for(self.name) or ""
        if gateway_txn and frappe.db.exists("Payment Transaction", {"gateway_txn_id": gateway_txn}):
            if self.status != "Paid":
                self.status = "Paid"
                self.save(ignore_permissions=True)
            # Retry/webhook repeat: transaction exists but fulfillment may never
            # have run (early-return used to skip it). Idempotent via fire() keys.
            _fulfill_order(self)
            return "/store/invoices"
        frappe.get_doc(
            {
                "doctype": "Payment Transaction",
                "invoice": self.name,
                "gateway": gateway,
                "gateway_txn_id": gateway_txn,
                "amount": self.total_due,
                "status": "Success",
                "raw_response": "{}",
            }
        ).insert(ignore_permissions=True)
        self.status = "Paid"
        self.save(ignore_permissions=True)
        _fulfill_order(self)
        return "/store/invoices"


def _invoice_context(inv) -> dict:
    return {"invoice": inv.name, "amount": inv.total_due, "customer": inv.customer, "order": inv.order_ref, "due": str(inv.due_date or "")}


def _plan_tax_info(ref: str | None) -> tuple:
    """(code, label) from the line's plan, via its Tax Code master."""
    try:
        plan = None
        if ref and frappe.db.exists("Service", ref):
            plan = frappe.db.get_value("Service", ref, "hosting_plan")
        elif ref and frappe.db.exists("Hosting Plan", ref):
            plan = ref
        if plan:
            code = frappe.db.get_value("Hosting Plan", plan, "tax_code") or ""
            if code and frappe.db.exists("Tax Code", code):
                return code, frappe.db.get_value("Tax Code", code, "label") or ""
            return code, ""
    except Exception:
        pass
    return "", ""


def _plan_tax_code(ref: str | None) -> str:
    """Seller-entered tax code (SAC/HSN/...) for a line ref. Blank when unknown."""
    return _plan_tax_info(ref)[0]


def _plan_tax_code_label(ref: str | None) -> str:
    """Header label from the line's plan master. Blank when unknown."""
    return _plan_tax_info(ref)[1]


def _notify_invoice(doc, is_renewal: bool = False):
    """Best-effort invoice + renewal + credit notices. Never breaks billing."""
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        ctx = _invoice_context(doc)
        notify_customer(doc.customer, "invoice", doc.name, ctx)
        if is_renewal:
            notify_customer(doc.customer, "renewal", f"{doc.name}:renewal", ctx)
        if (doc.credit_applied or 0) > 0:
            notify_customer(doc.customer, "credit", f"{doc.name}:credit", ctx)
    except Exception:
        pass


def _is_upgrade_order(order_name: str) -> bool:
    """Upgrade orders carry upgrade_of in a Hosting Plan snapshot."""
    import json

    try:
        order = frappe.get_doc("Order", order_name)
    except Exception:
        return False
    for item in order.items or []:
        if item.get("item_type") != "Hosting Plan":
            continue
        try:
            snap = json.loads(item.get("configuration_snapshot") or "{}")
        except Exception:
            continue
        if snap.get("upgrade_of"):
            return True
    return False


def _fulfill_order(inv):
    """WHMCS steps 9-10: services, domains, provisioning, welcome emails.

    Idempotent: create_from_order only adds missing hosting services,
    domain calls reuse existing Domain rows, notifications dedupe by key.
    Upgrade invoices skip new-service creation; on_invoice_paid swaps plan.
    """
    from lube_station.lube_station.notifications.events import notify_customer

    order_name = inv.order_ref
    ctx = _invoice_context(inv)
    if order_name and frappe.db.exists("Order", order_name):
        frappe.db.set_value("Order", order_name, "status", "Accepted")
        try:
            from lube_station.lube_provisioning.doctype.service.service import create_from_order, on_invoice_paid

            if _is_upgrade_order(order_name):
                on_invoice_paid(inv.name)
            else:
                if not frappe.db.exists("Service", {"order_ref": order_name}):
                    create_from_order(order_name)
                on_invoice_paid(inv.name)
        except Exception:
            pass
        if not _is_upgrade_order(order_name):
            _fulfill_domains(order_name, inv.customer)
    for svc in frappe.get_all("Service", {"order_ref": order_name} if order_name else {"customer": inv.customer}, ["name", "hosting_plan"]):
        try:
            module = frappe.db.get_value("Hosting Plan", svc.hosting_plan, "provisioning_module")
            if module:
                frappe.get_doc("Provisioning Module", module).create_account(svc.name)
        except Exception:
            pass
    try:
        notify_customer(inv.customer, "payment", inv.name, ctx)
        notify_customer(inv.customer, "credentials", f"{inv.name}:creds", ctx)
    except Exception:
        pass


def notify_payment_failed(invoice: str, reason: str = ""):
    """WHMCS payment-failed notice. Safe to call from webhooks/auto-charge."""
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        inv = frappe.get_doc("Hosting Invoice", invoice)
        notify_customer(inv.customer, "payment_failed", f"{invoice}:failed", {**_invoice_context(inv), "reason": reason})
    except Exception:
        pass


def _fulfill_domains(order_name: str, customer: str):
    """Register/transfer ordered domains, link owned ones to the customer."""
    import json

    from lube_station.lube_domains.doctype.registered_domain.registered_domain import register_domain, transfer_domain

    order = frappe.get_doc("Order", order_name)
    for item in order.items:
        if item.item_type == "Domain":
            try:
                config = json.loads(item.configuration_snapshot or "{}")
            except Exception:
                config = {}
            action = config.get("domain_action", "register")
            years = config.get("domain_years") or item.quantity or 1
            try:
                if action == "transfer":
                    transfer_domain(item.reference, config.get("epp") or "", None, customer)
                elif action == "register":
                    register_domain(item.reference, customer, None, years)
            except Exception:
                pass
        elif item.item_type == "Hosting Plan" and item.reference:
            try:
                config = json.loads(item.configuration_snapshot or "{}")
            except Exception:
                config = {}
            action = config.get("domain_action")
            if action in ("register", "transfer") and config.get("_domain"):
                try:
                    if action == "transfer":
                        transfer_domain(config["_domain"], config.get("epp") or "", None, customer)
                    else:
                        register_domain(config["_domain"], customer, None, config.get("domain_years") or 1)
                except Exception:
                    pass
            elif action == "own" and config.get("_domain") and not frappe.db.exists("Registered Domain", config["_domain"]):
                try:
                    frappe.get_doc({"doctype": "Registered Domain", "domain_name": config["_domain"], "customer": customer, "status": "Active"}).insert(ignore_permissions=True)
                except Exception:
                    pass
            # subdomain: seller-zone name, no registrar call and no Domain row
            # (renewal flow must never touch it); lives as Service.primary_domain.


def _from_order(order_name: str, key: str, gateway: str | None = None, include_setup: bool = True):
    order = frappe.get_doc("Order", order_name)
    customer = order.customer
    if not customer:
        frappe.throw("Order has no customer")
    items = [
        {
            "description": f"{i.item_type}: {i.reference} x{i.quantity}",
            "service_ref": i.reference,
            "amount": (i.unit_price or 0) * (i.quantity or 1),
            "tax_code": _plan_tax_info(i.reference)[0],
            "tax_code_label": _plan_tax_info(i.reference)[1],
        }
        for i in order.items
    ]
    if include_setup:
        # WHMCS setup fee: first invoice only, never on renewals.
        for i in order.items:
            if i.item_type != "Hosting Plan" or not i.reference or not frappe.db.exists("Hosting Plan", i.reference):
                continue
            setup = frappe.db.get_value("Plan Pricing", {"hosting_plan": i.reference, "billing_cycle": i.billing_cycle}, "setup_fee") or 0
            if setup:
                code, lbl = _plan_tax_info(i.reference)
                items.append({"description": f"Setup fee: {i.reference} x{i.quantity}", "service_ref": i.reference, "amount": setup * (i.quantity or 1), "tax_code": code, "tax_code_label": lbl})
    items_total = sum(i["amount"] for i in items)
    # WHMCS per-product Apply Tax: hosting plans carry their own flag,
    # domain lines follow Settings; untaxed lines still bill, just tax-free.
    from lube_station.lube_station.settings import get_setting

    taxable_lines = []
    order_rows = list(order.items)
    for idx, entry in enumerate(items):
        if idx < len(order_rows):
            i = order_rows[idx]
            if i.item_type == "Domain":
                taxable = bool(get_setting("tax_domains"))
            elif i.item_type == "Hosting Plan" and frappe.db.exists("Hosting Plan", i.reference):
                taxable = frappe.db.get_value("Hosting Plan", i.reference, "taxable")
                taxable = True if taxable is None else bool(taxable)
            else:
                taxable = True
        else:
            # Setup-fee lines inherit the parent plan's tax flag.
            parent = next((o for o in order_rows if o.item_type == "Hosting Plan" and o.reference == entry.get("service_ref")), None)
            if parent is not None and frappe.db.exists("Hosting Plan", parent.reference):
                taxable = frappe.db.get_value("Hosting Plan", parent.reference, "taxable")
                taxable = True if taxable is None else bool(taxable)
            else:
                taxable = True
        taxable_lines.append({"amount": entry["amount"], "taxable": taxable})
    tax = 0
    subtotal = items_total
    label = "No tax"
    breakup = {"cgst": 0, "sgst": 0, "ugst": 0, "igst": 0}
    if frappe.db.exists("DocType", "Tax Rule"):
        from lube_station.lube_billing.doctype.tax_rule.tax_rule import tax_breakup

        out = tax_breakup(customer, taxable_lines)
        tax = out["total"]
        label = out["label"]
        breakup = out
        if (out["mode"] == "inclusive"):
            subtotal = round(items_total - tax, 2)
    credit = 0
    if frappe.db.exists("DocType", "Credit Note"):
        from lube_station.lube_customers.doctype.credit_note.credit_note import apply_credit

        credit = apply_credit(customer, items_total + tax)
    from lube_station.lube_station.settings import get_setting

    due_date = _whmcs_due_date(order_name, include_setup)

    doc = frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": customer,
            "order_ref": order_name,
            "invoice_items": items,
            "tax_amount": tax,
            "subtotal_amount": subtotal,
            "tax_label": label,
            "cgst_amount": breakup["cgst"],
            "sgst_amount": breakup["sgst"],
            "ugst_amount": breakup["ugst"],
            "igst_amount": breakup["igst"],
            "credit_applied": credit,
            "due_date": due_date,
            "status": "Unpaid",
            "gateway": gateway,
            "idempotency_key": key,
        }
    ).insert(ignore_permissions=True)
    if doc.total_due == 0 and credit:
        # Fully wallet-covered: no payment will arrive, settle reservation now.
        from lube_station.lube_customers.doctype.credit_note.credit_note import consume_credit

        consume_credit(doc.name, allow_unpaid_zero=True)
    _notify_invoice(doc, is_renewal=not include_setup)
    return doc


def _whmcs_due_date(order_name: str, include_setup: bool) -> str:
    """WHMCS due dates: initial invoices due on receipt (today); renewal
    invoices due on the services' Next Due Date (period boundary). Falls back
    to today + invoice_due_days when no service date exists (domain-only and
    legacy orders)."""
    from frappe.utils import getdate

    from lube_station.lube_station.settings import get_setting

    if include_setup:
        return today()
    try:
        dates = [
            getdate(r["next_due_date"])
            for r in frappe.db.get_all("Service", {"order_ref": order_name, "next_due_date": ["is", "set"]}, ["next_due_date"])
            if r.get("next_due_date")
        ]
    except Exception:
        dates = []
    if dates:
        return str(min(dates))
    return add_days(today(), get_setting("invoice_due_days") or 7)


def _paypal_txn_for(invoice_name: str) -> str | None:
    """Latest completed PayPal Integration Request txn for this invoice.

    PayPal's confirm_payment calls on_payment_authorized without flags data,
    so recover the transaction id from the request log.
    """
    import json

    rows = frappe.get_all(
        "Integration Request",
        {"integration_request_service": "PayPal", "status": "Completed"},
        ["data"],
        order_by="modified desc",
        limit=10,
    )
    for row in rows:
        try:
            logged = json.loads(row.data or "{}")
        except Exception:
            continue
        if logged.get("reference_docname") == invoice_name and logged.get("transaction_id"):
            return str(logged["transaction_id"])
    return None


@frappe.whitelist(methods=["POST"])
def generate_invoice(order: str, gateway: str | None = None) -> dict:
    order_doc = frappe.get_doc("Order", order)
    if "System Manager" not in frappe.get_roles() and frappe.session.user != "Administrator":
        from lube_station.lube_station.portal.guards import assert_owns

        assert_owns(order_doc.customer)
    key = f"init:{order}"
    if frappe.db.exists("Hosting Invoice", {"idempotency_key": key}):
        doc = frappe.get_doc("Hosting Invoice", {"idempotency_key": key})
        return {"invoice": doc.name, "total_due": doc.total_due, "reused": True}
    doc = _from_order(order, key, gateway)
    return {"invoice": doc.name, "total_due": doc.total_due, "reused": False}


@frappe.whitelist(methods=["POST"])
def generate_renewal(order: str, period: str, gateway: str | None = None) -> dict:
    key = f"renew:{order}:{period}"
    if frappe.db.exists("Hosting Invoice", {"idempotency_key": key}):
        doc = frappe.get_doc("Hosting Invoice", {"idempotency_key": key})
        return {"invoice": doc.name, "total_due": doc.total_due, "reused": True}
    doc = _from_order(order, key, gateway, include_setup=False)
    return {"invoice": doc.name, "total_due": doc.total_due, "reused": False}


@frappe.whitelist(methods=["POST"])
def issue_refund(invoice: str, amount: float | None = None, reason: str = "") -> dict:
    """WHMCS refund: credit customer balance + refund/credit emails.

    Restores both the gateway-charged total and any wallet credit consumed at
    payment, so the customer is made whole either way.
    """
    inv = frappe.get_doc("Hosting Invoice", invoice)
    if inv.status != "Paid":
        frappe.throw("Only Paid invoices can be refunded")
    refund_amount = float(amount or inv.total_due or 0) + float(inv.get("credit_consumed") or 0)
    if refund_amount <= 0:
        frappe.throw("Refund amount must be positive")
    credit_note = frappe.get_doc({"doctype": "Credit Note", "customer": inv.customer, "amount": refund_amount, "reason": reason, "reference_invoice": inv.name}).insert(ignore_permissions=True)
    try:
        credit_note.submit()
    except Exception:
        pass
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        ctx = {**_invoice_context(inv), "refund": refund_amount, "reason": reason}
        notify_customer(inv.customer, "refund", f"{invoice}:refund", ctx)
        notify_customer(inv.customer, "credit", f"{invoice}:refund-credit", ctx)
    except Exception:
        pass
    return {"refunded": refund_amount, "credit_note": credit_note.name}


def print_context(invoice_name: str) -> dict:
    """Enriched context for the 'Hosting Invoice' print format.

    Billing identity (name + address, never the raw customer ID),
    customer-facing line labels, purchased domain, and service period.
    Never raises: falls back to raw values on any miss.
    """
    from lube_station.lube_station.portal.apis import _enriched_items

    inv = frappe.get_doc("Hosting Invoice", invoice_name)
    try:
        cust = frappe.get_doc("Hosting Customer", inv.customer)
        contact = frappe.db.get_value("User", cust.user, ["full_name", "email"], as_dict=True) or {}
        from lube_station.lube_station.customers.addresses import billing_address_text

        address = billing_address_text(inv.customer) or cust.billing_address or ", ".join(
            p for p in (cust.address_line1, cust.city, cust.state, cust.postcode, cust.country) if p
        )
        billing = {
            "name": contact.get("full_name") or cust.user,
            "email": contact.get("email") or cust.user,
            "company": cust.company or "",
            "phone": cust.phone or "",
            "tax_id": cust.tax_id or "",
            "address": address or "",
        }
    except Exception:
        billing = {"name": inv.customer, "email": "", "company": "", "phone": "", "tax_id": "", "address": ""}
    try:
        items = _enriched_items(inv)
    except Exception:
        items = [i.as_dict() for i in inv.invoice_items]
    try:
        default_code = frappe.db.get_single_value("Lube Station Settings", "default_tax_code") or ""
    except Exception:
        default_code = ""
    for d in items:
        d.setdefault("title", d.get("description"))
        d.setdefault("meta", "")
        d.setdefault("domain", "")
        if not d.get("tax_code"):
            d["tax_code"] = _plan_tax_code(d.get("service_ref")) or default_code
        d["qty"] = _qty_value(d.get("description") or "")
        d["start"], d["end"] = _line_period_paid(inv, d.get("service_ref") or "")
    label = "Tax code"
    for d in items:
        if not d.get("tax_code"):
            continue
        if not d.get("tax_code_label"):
            d["tax_code_label"] = _plan_tax_code_label(d.get("service_ref"))
        if d.get("tax_code_label"):
            label = d["tax_code_label"]
            break
    try:
        seller_tax = frappe.db.get_single_value("Lube Station Settings", "company_tax_id") or frappe.db.get_single_value(
            "GST Settings", "gstin"
        )
    except Exception:
        seller_tax = ""
    seller = {
        "name": frappe.db.get_single_value("Lube Station Settings", "company_name") or "",
        "address": frappe.db.get_single_value("Lube Station Settings", "company_address") or "",
        "tax_id": seller_tax or "",
        "logo": frappe.db.get_single_value("Lube Station Settings", "company_logo") or "",
    }
    payment = {"gateway": inv.gateway or "", "txn_id": "", "show": inv.status == "Paid"}
    transactions = []
    try:
        transactions = frappe.db.get_all(
            "Payment Transaction",
            {"invoice": inv.name, "status": "Success"},
            ["gateway", "gateway_txn_id", "amount", "creation"],
            order_by="creation asc",
        ) or []
        if transactions:
            last = transactions[-1]
            payment = {
                "gateway": last.get("gateway") or inv.gateway or "",
                "txn_id": last.get("gateway_txn_id") or "",
                "show": True,
            }
    except Exception:
        transactions = []
    return {
        "billing": billing,
        "seller": seller,
        "tax_code_label": label,
        "lines": items,
        "transactions": transactions,
        "payment": payment,
        "status_color": STATUS_COLORS.get(inv.status, "#6b7280"),
    }


def _line_period_paid(inv, ref):
    """(start, end) display dates for one line.

    Unpaid invoices show no period: the service has not started.
    Paid invoices start on the first successful payment posting;
    the end follows the purchased billing cycle (service, else order).
    """
    if inv.status != "Paid":
        return "", ""
    try:
        from frappe.utils import add_months, getdate

        start = _paid_date(inv)
        if not start:
            return "", ""
        start_d = getdate(start)
        months = CYCLE_MONTHS.get(_line_cycle(inv, ref), 0)
        if not months:
            return _fmt_date(start_d), ""
        return _fmt_date(start_d), _fmt_date(add_months(start_d, months))
    except Exception:
        return "", ""


def _paid_date(inv):
    """First successful payment posting for the invoice. None when unknown."""
    try:
        hit = frappe.db.get_value(
            "Payment Transaction", {"invoice": inv.name, "status": "Success"}, "creation", order_by="creation asc"
        )
        if hit:
            return hit
        if inv.status == "Paid":
            return inv.modified
    except Exception:
        pass
    return None


def _line_cycle(inv, ref):
    """Billing cycle name for one line: service first, else matching order item."""
    try:
        if ref and frappe.db.exists("Service", ref):
            return frappe.db.get_value("Service", ref, "billing_cycle") or ""
        if inv.order_ref and frappe.db.exists("Order", inv.order_ref):
            for oi in frappe.get_doc("Order", inv.order_ref).items:
                if oi.reference == ref and oi.billing_cycle:
                    return oi.billing_cycle
    except Exception:
        pass
    return ""


def _qty_value(description):
    """Quantity parsed from the stored line ('... x2'). Blank when absent."""
    import re

    m = re.search(r" x(\d+)$", description or "")
    return int(m.group(1)) if m else ""


def _fmt_date(d):
    if not d:
        return ""
    try:
        from frappe.utils import formatdate

        return formatdate(d)
    except Exception:
        return str(d)
