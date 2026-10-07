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
    "Virtualizor": "lube_station.lube_station.adapters.provisioning.virtualizor.VirtualizorAdapter",
    "Proxmox VE": "lube_station.lube_station.adapters.provisioning.stubs.ProxmoxAdapter",
    "Hetzner Cloud": "lube_station.lube_station.adapters.provisioning.stubs.HetznerCloudAdapter",
    "AWS EC2": "lube_station.lube_station.adapters.provisioning.stubs.AwsEc2Adapter",
    "Cloudflare": "lube_station.lube_station.adapters.provisioning.stubs.CloudflareAdapter",
}

REGISTRAR_PATHS = {
    "OpenSRS": "lube_station.lube_station.adapters.registrar.opensrs.OpenSrsAdapter",
    "Namecheap": "lube_station.lube_station.adapters.registrar.namecheap.NamecheapAdapter",
    "GoDaddy": "lube_station.lube_station.adapters.registrar.godaddy.GodaddyAdapter",
    "ResellerClub / LogicBoxes": "lube_station.lube_station.adapters.registrar.logicboxes.LogicBoxesAdapter",
    "eNom": "lube_station.lube_station.adapters.registrar.enom.EnomAdapter",
    "CentralNic Reseller": "lube_station.lube_station.adapters.registrar.centralnic.CentralNicAdapter",
    "HEXONET": "lube_station.lube_station.adapters.registrar.hexonet.HexonetAdapter",
    "Porkbun": "lube_station.lube_station.adapters.registrar.porkbun.PorkbunAdapter",
    "Internet.bs": "lube_station.lube_station.adapters.registrar.internetbs.InternetBsAdapter",
    "Nominet": "lube_station.lube_station.adapters.registrar.nominet.NominetAdapter",
}


def _load(path: str):
    mod, cls = path.rsplit(".", 1)
    return getattr(importlib.import_module(mod), cls)()


def resolve_class_path(paths: dict, name: str, current: str | None) -> str | None:
    return current or paths.get(name)


def ensure_importable(path: str, label: str):
    try:
        mod_name, cls_name = path.rsplit(".", 1)
        module = importlib.import_module(mod_name)
        if not hasattr(module, cls_name):
            raise AttributeError(f"class '{cls_name}' not found")
    except (ImportError, AttributeError, ValueError) as e:
        frappe.throw(f"{label}: cannot import '{path}'. {e}")


PROVISIONING_LIFECYCLE = [
    "create_account",
    "suspend_account",
    "unsuspend_account",
    "terminate_account",
    "change_password",
    "change_package",
    "get_usage",
    "test_connection",
]


REGISTRAR_OPERATIONS = [
    "check_availability",
    "register_domain",
    "transfer_domain",
    "renew_domain",
    "get_domain_info",
    "update_nameservers",
    "create_dns_record",
    "update_dns_record",
    "delete_dns_record",
    "update_contact",
    "toggle_privacy",
]


def implemented_lifecycle(path: str, methods: list | None = None) -> list:
    """Method names the adapter class really implements.

    A method counts only when the class overrides it without raising
    NotImplementedError. No instance is created and nothing is called.
    """
    import inspect

    if methods is None:
        methods = PROVISIONING_LIFECYCLE
    try:
        mod_name, cls_name = path.rsplit(".", 1)
        cls = getattr(importlib.import_module(mod_name), cls_name)
    except (ImportError, AttributeError, ValueError):
        return []
    out = []
    for name in methods:
        fn = getattr(cls, name, None)
        if fn is None:
            continue
        try:
            source = inspect.getsource(fn)
        except (OSError, TypeError):
            out.append(name)
            continue
        if "NotImplementedError" not in source:
            out.append(name)
    return out


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
