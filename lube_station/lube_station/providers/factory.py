import frappe

from .manual import ManualAdapter


def get_provider_adapter(provider_name: str):
    provider = frappe.get_doc("Infrastructure Provider", provider_name)
    if provider.status != "Active":
        frappe.throw(f"{provider_name} not active")
    if provider.provider_type in ("Local Infrastructure", "Reseller Program") or not provider.api_base_url:
        return ManualAdapter()
    return ManualAdapter()
