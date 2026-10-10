import frappe
import json
from frappe.model.document import Document
from frappe.utils import add_to_date, today


def _log(doc, msg: str):
    doc.provisioning_log = ((doc.provisioning_log or "") + f"\n{msg}").strip()[-2000:]
    doc.save(ignore_permissions=True)


def _notify(doc, event_type: str, context: dict | None = None, template: str | None = None):
    """Best-effort customer email; lifecycle never fails on mail errors."""
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        ctx = {"service": doc.name, "plan": doc.get("hosting_plan"), "domain": doc.get("primary_domain")}
        if context:
            ctx.update(context)
        notify_customer(doc.get("customer"), event_type, doc.name, ctx, template)
    except Exception:
        pass


def _welcome_template(plan: str | None) -> str | None:
    if not plan or not frappe.db.exists("Hosting Plan", plan):
        return None
    try:
        tpl = frappe.db.get_value("Hosting Plan", plan, "welcome_email_template")
        return tpl or None
    except Exception:
        return None


class Service(Document):
    def activate(self):
        if self.status == "Terminated":
            frappe.throw("Terminated services stay terminated")
        was = self.status
        self.status = "Active"
        self.save(ignore_permissions=True)
        _log(self, "activated")
        if was == "Pending":
            _notify(self, "welcome", template=_welcome_template(self.get("hosting_plan")))
            _notify(self, "credentials", {"note": "Login via portal vault, no password in email"})
        elif was == "Suspended":
            _notify(self, "unsuspension")

    def suspend(self, reason: str = ""):
        if self.status != "Active":
            frappe.throw(f"Cannot suspend from {self.status}")
        self.status = "Suspended"
        self.save(ignore_permissions=True)
        _log(self, f"suspended {reason}")
        _notify(self, "suspension", {"reason": reason})
        _cascade(self, "suspend", reason)

    def unsuspend(self):
        if self.status != "Suspended":
            frappe.throw(f"Cannot unsuspend from {self.status}")
        self.status = "Active"
        self.save(ignore_permissions=True)
        _log(self, "unsuspended")
        _notify(self, "unsuspension")
        # No cascade: add-ons suspended for their own overdue invoices must
        # reactivate via their own payment, not the parent's.

    def terminate(self, approval_note: str | None = None):
        if not approval_note:
            frappe.throw("Termination needs approval note")
        self.status = "Terminated"
        self.save(ignore_permissions=True)
        _log(self, f"terminated: {approval_note}")
        _notify(self, "termination", {"reason": approval_note})
        _notify(self, "cancellation_confirm", {"reason": approval_note})
        _cascade(self, "terminate", approval_note)


def _cascade(parent, action: str, reason: str):
    """WHMCS add-on lifecycle: children follow parent suspend/terminate."""
    for row in frappe.get_all("Service", {"parent_service": parent.name}, ["name", "status"]):
        try:
            child = frappe.get_doc("Service", row.name)
        except Exception:
            continue
        try:
            if action == "suspend" and child.status == "Active":
                child.suspend(f"parent {parent.name} suspended: {reason}")
            elif action == "terminate" and child.status not in ("Terminated", "Cancelled"):
                child.terminate(f"parent {parent.name} terminated: {reason}")
        except Exception:
            continue


@frappe.whitelist(methods=["POST"])
def create_from_order(order: str) -> dict:
    order_doc = frappe.get_doc("Order", order)
    if not order_doc.customer:
        frappe.throw("Order has no customer")
    made = []
    for item in order_doc.items:
        if item.item_type != "Hosting Plan" or not frappe.db.exists("Hosting Plan", item.reference):
            continue
        plan = frappe.get_doc("Hosting Plan", item.reference)
        price = frappe.db.get_value("Plan Pricing", {"hosting_plan": plan.name, "billing_cycle": item.billing_cycle}, "recurring_amount") or item.unit_price
        kwargs = {"doctype": "Service", "customer": order_doc.customer, "hosting_plan": plan.name, "order_ref": order, "billing_cycle": item.billing_cycle, "status": "Pending", "next_due_date": add_to_date(today(), months=1), "recurring_amount": price}
        if getattr(item, "parent_service", None):
            parent = frappe.get_doc("Service", item.parent_service)
            if parent.customer != order_doc.customer:
                frappe.throw("Add-on parent belongs to another customer")
            kwargs["parent_service"] = parent.name
        try:
            attached = (json.loads(item.configuration_snapshot or "{}") or {}).get("_domain")
        except Exception:
            attached = None
        if attached:
            # WHMCS parity: the ordered domain (or free subdomain) names the
            # service for provisioning (cPanel account, hostname, zone).
            kwargs["primary_domain"] = attached
        svc = frappe.get_doc(kwargs).insert(ignore_permissions=True)
        made.append(svc.name)
    return {"services": made}


@frappe.whitelist(methods=["POST"])
def on_invoice_paid(invoice: str) -> dict:
    inv = frappe.get_doc("Hosting Invoice", invoice)
    if inv.status != "Paid":
        return {"action": "none"}
    # Upgrade invoices: swap plan automatically once balance is paid.
    # Idempotent: already-swapped services are skipped.
    upgraded = _apply_upgrade_for_invoice(inv)
    out = []
    if inv.order_ref:
        for svc in frappe.get_all("Service", {"order_ref": inv.order_ref}, ["name", "status"]):
            # Upgrade orders own no Service rows (order_ref points at the
            # upgrade order, not the original service order).
            if any(u["service"] == svc["name"] for u in upgraded):
                continue
            doc = frappe.get_doc("Service", svc.name)
            if doc.status == "Pending":
                doc.activate()
                out.append(doc.name)
            elif doc.status == "Suspended":
                doc.unsuspend()
                out.append(doc.name)
    if upgraded:
        return {"action": "upgraded", "services": [u["service"] for u in upgraded]}
    if not out and inv.order_ref:
        # Renewal payment: services already Active, confirm renewal.
        try:
            from lube_station.lube_station.notifications.events import notify_customer

            for svc in frappe.get_all("Service", {"order_ref": inv.order_ref}, ["name", "customer", "next_due_date"]):
                notify_customer(svc.customer, "renewal_confirm", invoice, {"service": svc.name, "next_due": str(svc.get("next_due_date") or "")})
        except Exception:
            pass
    return {"action": "activated", "services": out}


def _apply_upgrade_for_invoice(inv) -> list:
    """Apply portal upgrade swap for a Paid upgrade invoice."""
    import json

    if not inv.get("order_ref") or not frappe.db.exists("Order", inv.order_ref):
        # Fallback: idempotency key upgrade:{service}:{plan}.
        key = inv.get("idempotency_key") or ""
        if key.startswith("upgrade:"):
            try:
                _, svc_name, plan = key.split(":", 2)
                if frappe.db.exists("Service", svc_name) and frappe.db.exists("Hosting Plan", plan):
                    from lube_station.lube_station.portal.apis import _apply_plan_swap

                    if frappe.db.get_value("Service", svc_name, "hosting_plan") != plan:
                        _apply_plan_swap(svc_name, plan, invoice_name=inv.name)
                        return [{"service": svc_name}]
            except Exception:
                pass
        return []
    try:
        order = frappe.get_doc("Order", inv.order_ref)
    except Exception:
        return []
    done = []
    for item in order.items or []:
        if item.get("item_type") != "Hosting Plan":
            continue
        try:
            snap = json.loads(item.get("configuration_snapshot") or "{}")
        except Exception:
            snap = {}
        svc_name = snap.get("upgrade_of")
        new_plan = snap.get("upgrade_to") or item.get("reference")
        if not svc_name or not new_plan or not frappe.db.exists("Service", svc_name):
            continue
        try:
            from lube_station.lube_station.portal.apis import _apply_plan_swap

            if frappe.db.get_value("Service", svc_name, "hosting_plan") != new_plan:
                _apply_plan_swap(svc_name, new_plan, invoice_name=inv.name)
            done.append({"service": svc_name})
        except Exception:
            continue
    return done


@frappe.whitelist(methods=["POST"])
def apply_dunning(invoice: str) -> dict:
    from lube_station.lube_billing.doctype.dunning_rule.dunning_rule import evaluate_invoice

    result = evaluate_invoice(invoice)
    inv = frappe.get_doc("Hosting Invoice", invoice)
    try:
        from lube_station.lube_station.notifications.events import notify_customer

        ctx = {"invoice": invoice, "overdue_days": result.get("overdue_days", 0)}
        if result["action"] == "notify":
            notify_customer(inv.customer, "invoice_reminder", f"{invoice}:reminder", ctx)
        elif result["action"] == "suspend":
            notify_customer(inv.customer, "overdue_first", f"{invoice}:overdue1", ctx)
        elif result["action"] == "queue_termination":
            notify_customer(inv.customer, "overdue_third", f"{invoice}:overdue3", ctx)
    except Exception:
        pass
    if not inv.order_ref:
        return result
    if result["action"] == "suspend":
        for svc in frappe.get_all("Service", {"order_ref": inv.order_ref, "status": "Active"}, ["name"]):
            frappe.get_doc("Service", svc.name).suspend(f"invoice {invoice} overdue")
    return result
