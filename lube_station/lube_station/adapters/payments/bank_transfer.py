"""Live Bank Transfer adapter: real offline workflow, no vendor API.

create_payment records an idempotent Pending transaction keyed by invoice and
returns instructions carrying the payment reference plus the seller's bank
details (Lube Station Settings). Staff approve via approve_bank_transfer,
which flips the transaction and marks the invoice paid (unsuspending
services). Verification reads the transaction state. Refunds stay manual;
tokenization and auto-charge are correctly unsupported.
"""

import frappe

from lube_station.lube_station.settings import get_setting

from .base import PaymentGatewayAdapter


def _reference(invoice_name: str) -> str:
    return f"BT-{invoice_name}"


class BankTransferAdapter(PaymentGatewayAdapter):
    adapter_name = "Bank Transfer"

    def create_payment(self, invoice):
        inv = frappe.get_doc("Hosting Invoice", invoice) if isinstance(invoice, str) else invoice
        if inv.status == "Paid":
            frappe.throw("Invoice already paid")
        reference = _reference(inv.name)
        existing = frappe.db.get_value(
            "Payment Transaction", {"gateway": "Bank Transfer", "gateway_txn_id": reference}, "name"
        )
        if not existing:
            frappe.get_doc(
                {
                    "doctype": "Payment Transaction",
                    "invoice": inv.name,
                    "gateway": "Bank Transfer",
                    "gateway_txn_id": reference,
                    "amount": inv.total_due,
                    "status": "Pending",
                    "raw_response": "{}",
                }
            ).insert(ignore_permissions=True)
        bank = (get_setting("bank_details") or "").strip()
        lines = [
            f"Transfer {inv.total_due} with reference {reference}.",
            f"Bank details: {bank}" if bank else "Bank details are shown by the seller after checkout.",
            "Share the transfer receipt; staff approve the invoice on receipt.",
        ]
        return {"gateway": "Bank Transfer", "invoice": inv.name, "manual": True, "reference": reference, "instructions": " ".join(lines)}

    def verify_payment(self, payload):
        invoice = (payload or {}).get("invoice") or (payload or {}).get("invoice_name") or ""
        name = frappe.db.get_value(
            "Payment Transaction",
            {"gateway": "Bank Transfer", "invoice": invoice},
            ["status", "gateway_txn_id"],
            as_dict=True,
        ) if invoice else None
        verified = bool(name and name.status == "Success")
        return {"verified": verified, "gateway_reference": (name or {}).get("gateway_txn_id") if isinstance(name, dict) else None}

    def handle_webhook(self, payload, headers):
        frappe.throw("Bank transfer has no webhooks")

    def refund_payment(self, transaction, amount=None):
        return {"refunded": transaction, "amount": amount, "manual": True}

    def create_payment_method(self, customer, token):
        frappe.throw("Bank transfer supports no tokenization")

    def charge_saved_method(self, payment_method, invoice):
        frappe.throw("Bank transfer supports no auto-charge")
