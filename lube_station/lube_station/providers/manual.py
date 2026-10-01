import frappe

from .base import ProviderAdapter, audit, with_retry


class ManualAdapter(ProviderAdapter):
    provider_name = "Manual"

    def _product(self, product: str):
        return frappe.get_doc("Provider Product", product)

    def test_connection(self):
        return {"ok": True}

    def list_regions(self):
        return []

    def list_images(self):
        return []

    def list_plans(self):
        return []

    def allocate_inventory(self, product: str, key: str):
        def _run():
            doc = self._product(product)
            if (doc.available_quantity or 0) <= 0:
                raise ValueError("No inventory")
            doc.available_quantity -= 1
            doc.save(ignore_permissions=True)
            return {"allocated": product}

        out = with_retry(_run)
        audit(doc.provider if (doc := self._product(product)) else product, "allocate", key)
        return out

    def create_instance(self, product: str, config: dict, key: str):
        return {"instance": key, "manual": True}

    def suspend(self, instance: str):
        return {"suspended": instance, "manual": True}

    def unsuspend(self, instance: str):
        return {"unsuspended": instance, "manual": True}

    def terminate(self, instance: str):
        return {"terminated": instance, "manual": True}

    def get_usage(self, instance: str):
        return {"disk": 0, "bandwidth": 0}

    def release_inventory(self, product: str, key: str):
        doc = self._product(product)
        doc.available_quantity = (doc.available_quantity or 0) + 1
        doc.save(ignore_permissions=True)
        audit(doc.provider, "release", f"{key}-release")
        return {"released": product}
