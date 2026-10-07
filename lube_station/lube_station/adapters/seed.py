"""Seed vendor registry rows. Idempotent."""

import frappe

PAYMENTS = [
    ("Stripe", "Stripe", "lube_station.lube_station.adapters.payments.stripe.StripeAdapter", 1, 1, 1, 1, 1, 1),
    ("Razorpay", "Razorpay", "lube_station.lube_station.adapters.payments.razorpay.RazorpayAdapter", 1, 1, 1, 1, 0, 1),
    ("PayPal Checkout", "PayPal", "lube_station.lube_station.adapters.payments.paypal.PayPalCheckoutAdapter", 1, 1, 0, 1, 0, 1),
    ("Bank Transfer", "Manual", "lube_station.lube_station.adapters.payments.bank_transfer.BankTransferAdapter", 1, 0, 0, 0, 0, 1),
    ("CCAvenue", "CCAvenue", "lube_station.lube_station.adapters.payments.stubs.CCAvenueAdapter", 0, 0, 0, 0, 0, 0),
    ("PayU India", "PayU", "lube_station.lube_station.adapters.payments.stubs.PayUIndiaAdapter", 0, 0, 0, 0, 0, 0),
    ("Cashfree Payments", "Cashfree", "lube_station.lube_station.adapters.payments.stubs.CashfreeAdapter", 0, 0, 0, 0, 0, 0),
    ("Mollie", "Mollie", "lube_station.lube_station.adapters.payments.stubs.MollieAdapter", 0, 0, 0, 0, 0, 0),
    ("GoCardless", "GoCardless", "lube_station.lube_station.adapters.payments.stubs.GoCardlessAdapter", 0, 0, 0, 0, 0, 0),
    ("2Checkout / Verifone", "2Checkout", "lube_station.lube_station.adapters.payments.stubs.TwoCheckoutAdapter", 0, 0, 0, 0, 0, 0),
]

PROVISIONING = [
    ("cPanel / WHM", "cPanel", "lube_station.lube_station.adapters.provisioning.cpanel.CpanelWhmAdapter", "WHM API", 1),
    ("Plesk", "Plesk", "lube_station.lube_station.adapters.provisioning.plesk.PleskAdapter", "XML API", 1),
    ("DirectAdmin", "DirectAdmin", "lube_station.lube_station.adapters.provisioning.directadmin.DirectAdminAdapter", "HTTP API", 1),
    ("Virtualizor", "Virtualizor", "lube_station.lube_station.adapters.provisioning.stubs.VirtualizorAdapter", "", 0),
    ("Proxmox VE", "Proxmox", "lube_station.lube_station.adapters.provisioning.stubs.ProxmoxAdapter", "", 0),
    ("Hetzner Cloud", "Hetzner", "lube_station.lube_station.adapters.provisioning.stubs.HetznerCloudAdapter", "", 0),
    ("AWS EC2", "AWS", "lube_station.lube_station.adapters.provisioning.stubs.AwsEc2Adapter", "", 0),
    ("Cloudflare", "Cloudflare", "lube_station.lube_station.adapters.provisioning.stubs.CloudflareAdapter", "", 0),
]

REGISTRARS = [
    ("OpenSRS", "OpenSRS", "REST", 1),
    ("Namecheap", "Namecheap", "REST", 1),
    ("GoDaddy", "GoDaddy", "REST", 1),
    ("ResellerClub / LogicBoxes", "LogicBoxes", "REST", 1),
    ("eNom", "eNom", "REST", 0),
    ("CentralNic Reseller", "CentralNic", "EPP", 0),
    ("HEXONET", "HEXONET", "EPP", 0),
    ("Porkbun", "Porkbun", "REST", 0),
    ("Internet.bs", "Internet.bs", "REST", 0),
    ("Nominet", "Nominet", "EPP", 0),
]


def seed():
    for name, vendor, path, ot, rec, tok, ref, pref, active in PAYMENTS:
        if not frappe.db.exists("Payment Gateway Adapter", name):
            frappe.get_doc(
                {
                    "doctype": "Payment Gateway Adapter",
                    "adapter_name": name,
                    "vendor_name": vendor,
                    "class_path": path,
                    "supports_one_time": ot,
                    "supports_recurring": rec,
                    "supports_tokenization": tok,
                    "supports_refunds": ref,
                    "supports_partial_refunds": pref,
                    "sandbox_supported": 1,
                    "active": active,
                }
            ).insert(ignore_permissions=True)
    for name, vendor, path, mode, active in PROVISIONING:
        if not frappe.db.exists("Provisioning Adapter", name):
            frappe.get_doc(
                {
                    "doctype": "Provisioning Adapter",
                    "adapter_name": name,
                    "vendor_name": vendor,
                    "class_path": path,
                    "api_mode": mode,
                    "supports_usage": 1,
                    "supports_change_plan": 1,
                    "active": active,
                }
            ).insert(ignore_permissions=True)
            continue
        doc = frappe.get_doc("Provisioning Adapter", name)
        dirty = False
        if mode and not doc.api_mode:
            doc.api_mode = mode
            dirty = True
        if doc.class_path and not doc.lifecycle_methods:
            dirty = True
        if dirty:
            doc.save(ignore_permissions=True)
    registrar_paths = {
        "OpenSRS": "lube_station.lube_station.adapters.registrar.opensrs.OpenSrsAdapter",
        "Namecheap": "lube_station.lube_station.adapters.registrar.namecheap.NamecheapAdapter",
        "GoDaddy": "lube_station.lube_station.adapters.registrar.mvp.GodaddyAdapter",
        "ResellerClub / LogicBoxes": "lube_station.lube_station.adapters.registrar.mvp.LogicBoxesAdapter",
        "eNom": "lube_station.lube_station.adapters.registrar.stubs.EnomAdapter",
        "CentralNic Reseller": "lube_station.lube_station.adapters.registrar.stubs.CentralNicAdapter",
        "HEXONET": "lube_station.lube_station.adapters.registrar.stubs.HexonetAdapter",
        "Porkbun": "lube_station.lube_station.adapters.registrar.stubs.PorkbunAdapter",
        "Internet.bs": "lube_station.lube_station.adapters.registrar.stubs.InternetBsAdapter",
        "Nominet": "lube_station.lube_station.adapters.registrar.stubs.NominetAdapter",
    }
    for name, vendor, mode, active in REGISTRARS:
        if not frappe.db.exists("Registrar Adapter", name):
            frappe.get_doc(
                {
                    "doctype": "Registrar Adapter",
                    "adapter_name": name,
                    "vendor_name": vendor,
                    "class_path": registrar_paths[name],
                    "api_mode": mode,
                    "supports_dns": 1,
                    "supports_privacy": 1,
                    "supports_transfer": 1,
                    "sandbox_supported": 1,
                    "active": active,
                }
            ).insert(ignore_permissions=True)
            continue
        doc = frappe.get_doc("Registrar Adapter", name)
        if doc.class_path and not doc.supported_operations:
            doc.save(ignore_permissions=True)
        # One-way upgrades: mock adapters -> live ones. Guarded by exact
        # legacy paths so seller-switched classes are never overwritten.
        for legacy, new in (
            (
                "OpenSRS",
                "lube_station.lube_station.adapters.registrar.mvp.OpenSrsAdapter",
            ),
            (
                "Namecheap",
                "lube_station.lube_station.adapters.registrar.mvp.NamecheapAdapter",
            ),
        ):
            if name == legacy and doc.class_path == new:
                doc.class_path = registrar_paths[name]
                doc.save(ignore_permissions=True)
