import frappe
from frappe.model.document import Document
from frappe.utils import add_days, today


class HostingInvoice(Document):
    def validate(self):
        items_total = sum(i.amount or 0 for i in self.invoice_items)
        subtotal = self.subtotal_amount if self.subtotal_amount else items_total
        self.total_due = max(subtotal + (self.tax_amount or 0) - (self.credit_applied or 0), 0)

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
    items = [{"description": f"{i.item_type}: {i.reference} x{i.quantity}", "service_ref": i.reference, "amount": (i.unit_price or 0) * (i.quantity or 1)} for i in order.items]
    if include_setup:
        # WHMCS setup fee: first invoice only, never on renewals.
        for i in order.items:
            if i.item_type != "Hosting Plan" or not i.reference or not frappe.db.exists("Hosting Plan", i.reference):
                continue
            setup = frappe.db.get_value("Plan Pricing", {"hosting_plan": i.reference, "billing_cycle": i.billing_cycle}, "setup_fee") or 0
            if setup:
                items.append({"description": f"Setup fee: {i.reference} x{i.quantity}", "service_ref": i.reference, "amount": setup * (i.quantity or 1)})
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
            "due_date": add_days(today(), get_setting("invoice_due_days") or 7),
            "status": "Unpaid",
            "gateway": gateway,
            "idempotency_key": key,
        }
    ).insert(ignore_permissions=True)
    _notify_invoice(doc, is_renewal=not include_setup)
    return doc


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
    """WHMCS refund: credit customer balance + refund/credit emails."""
    inv = frappe.get_doc("Hosting Invoice", invoice)
    if inv.status != "Paid":
        frappe.throw("Only Paid invoices can be refunded")
    refund_amount = float(amount or inv.total_due or 0)
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
