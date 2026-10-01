import time

import frappe


class ProviderError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ProviderAdapter:
    provider_name = ""

    def test_connection(self):
        raise NotImplementedError

    def list_regions(self):
        raise NotImplementedError

    def list_images(self):
        raise NotImplementedError

    def list_plans(self):
        raise NotImplementedError

    def allocate_inventory(self, product: str, key: str):
        raise NotImplementedError

    def create_instance(self, product: str, config: dict, key: str):
        raise NotImplementedError

    def suspend(self, instance: str):
        raise NotImplementedError

    def unsuspend(self, instance: str):
        raise NotImplementedError

    def terminate(self, instance: str):
        raise NotImplementedError

    def get_usage(self, instance: str):
        raise NotImplementedError

    def release_inventory(self, product: str, key: str):
        raise NotImplementedError


def with_retry(fn, retries: int = 3):
    last = None
    for attempt in range(retries):
        try:
            return fn()
        except Exception as e:
            last = e
            time.sleep(2**attempt)
    raise ProviderError("PROVIDER_FAILED", str(last))


def audit(provider: str, action: str, key: str, status: str = "Success", error: str = ""):
    if frappe.db.exists("Provider API Log", {"idempotency_key": key}):
        return frappe.get_doc("Provider API Log", {"idempotency_key": key})
    return frappe.get_doc({"doctype": "Provider API Log", "provider": provider, "action": action, "status": status, "error_text": error[:500] if error else "", "idempotency_key": key}).insert(ignore_permissions=True)
