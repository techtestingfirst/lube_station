import importlib

import frappe

PAYMENT_PATHS = {
    "Stripe": "lube_station.lube_station.adapters.payments.stripe.StripeAdapter",
    "Razorpay": "lube_station.lube_station.adapters.payments.razorpay.RazorpayAdapter",
    "PayPal Checkout": "lube_station.lube_station.adapters.payments.paypal.PayPalCheckoutAdapter",
    "Bank Transfer": "lube_station.lube_station.adapters.payments.bank_transfer.BankTransferAdapter",
    "CCAvenue": "lube_station.lube_station.adapters.payments.stubs.CCAvenueAdapter",
    "PayU India": "lube_station.lube_station.adapters.payments.stubs.PayUIndiaAdapter",
    "Cashfree Payments": "lube_station.lube_station.adapters.payments.stubs.CashfreeAdapter",
    "Mollie": "lube_station.lube_station.adapters.payments.stubs.MollieAdapter",
    "GoCardless": "lube_station.lube_station.adapters.payments.stubs.GoCardlessAdapter",
    "2Checkout / Verifone": "lube_station.lube_station.adapters.payments.stubs.TwoCheckoutAdapter",
}

PROVISIONING_PATHS = {
    "cPanel / WHM": "lube_station.lube_station.adapters.provisioning.cpanel.CpanelWhmAdapter",
    "Plesk": "lube_station.lube_station.adapters.provisioning.plesk.PleskAdapter",
    "DirectAdmin": "lube_station.lube_station.adapters.provisioning.directadmin.DirectAdminAdapter",
    "Virtualizor": "lube_station.lube_station.adapters.provisioning.stubs.VirtualizorAdapter",
    "Proxmox VE": "lube_station.lube_station.adapters.provisioning.stubs.ProxmoxAdapter",
    "Hetzner Cloud": "lube_station.lube_station.adapters.provisioning.stubs.HetznerCloudAdapter",
    "AWS EC2": "lube_station.lube_station.adapters.provisioning.stubs.AwsEc2Adapter",
    "Cloudflare": "lube_station.lube_station.adapters.provisioning.stubs.CloudflareAdapter",
}

REGISTRAR_PATHS = {
    "OpenSRS": "lube_station.lube_station.adapters.registrar.mvp.OpenSrsAdapter",
    "Namecheap": "lube_station.lube_station.adapters.registrar.mvp.NamecheapAdapter",
    "GoDaddy": "lube_station.lube_station.adapters.registrar.mvp.GodaddyAdapter",
    "ResellerClub / LogicBoxes": "lube_station.lube_station.adapters.registrar.mvp.LogicBoxesAdapter",
    "eNom": "lube_station.lube_station.adapters.registrar.stubs.EnomAdapter",
    "CentralNic Reseller": "lube_station.lube_station.adapters.registrar.stubs.CentralNicAdapter",
    "HEXONET": "lube_station.lube_station.adapters.registrar.stubs.HexonetAdapter",
    "Porkbun": "lube_station.lube_station.adapters.registrar.stubs.PorkbunAdapter",
    "Internet.bs": "lube_station.lube_station.adapters.registrar.stubs.InternetBsAdapter",
    "Nominet": "lube_station.lube_station.adapters.registrar.stubs.NominetAdapter",
}


def _load(path: str):
    mod, cls = path.rsplit(".", 1)
    return getattr(importlib.import_module(mod), cls)()


def _active_only(doctype: str, name: str, paths: dict):
    record = frappe.get_doc(doctype, name)
    if not record.get("active"):
        frappe.throw(f"{name} adapter inactive")
    path = paths.get(name) or record.get("class_path")
    return _load(path)


def get_payment_adapter(gateway_name: str):
    return _active_only("Payment Gateway Adapter", gateway_name, PAYMENT_PATHS)


def get_provisioning_adapter(adapter_name: str):
    return _active_only("Provisioning Adapter", adapter_name, PROVISIONING_PATHS)


def get_registrar_adapter(adapter_name: str):
    return _active_only("Registrar Adapter", adapter_name, REGISTRAR_PATHS)
