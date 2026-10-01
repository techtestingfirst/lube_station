import json

import frappe
from frappe.model.document import Document


class VPSInstance(Document):
    def validate(self):
        if self.configuration:
            cfg = frappe.get_doc("VPS Configuration", self.configuration)
            images = json.loads(cfg.os_images_json or "[]")
            locations = json.loads(cfg.locations_json or "[]")
            if images and self.image not in images:
                frappe.throw(f"Image {self.image} not in plan")
            if locations and self.location not in locations:
                frappe.throw(f"Location {self.location} not in plan")


def _paid(order: str) -> bool:
    return bool(frappe.db.exists("Hosting Invoice", {"order_ref": order, "status": "Paid"}))


def _audit(instance: str, action: str, key: str):
    inst = frappe.get_doc("VPS Instance", instance)
    provider = inst.provider or "Manual"
    if frappe.db.exists("DocType", "Provider API Log") and inst.provider:
        from lube_station.lube_station.providers.base import audit

        audit(inst.provider, f"vps:{action}", key)
    return {"instance": instance, "action": action}


@frappe.whitelist(methods=["POST"])
def create_vps_instance(order: str, configuration: str, image: str, location: str, provider: str | None = None) -> dict:
    if not _paid(order):
        frappe.throw("Order unpaid, cannot provision VPS")
    if not image or not location:
        frappe.throw("Image and location required")
    inst = frappe.get_doc({"doctype": "VPS Instance", "configuration": configuration, "order_ref": order, "provider": provider, "image": image, "location": location, "status": "Active"}).insert()
    _audit(inst.name, "create", f"vps-create:{inst.name}")
    return {"instance": inst.name}


@frappe.whitelist(methods=["POST"])
def vps_action(instance: str, action: str, arg: str | None = None) -> dict:
    allowed = {"rebuild", "start", "stop", "reboot", "snapshot", "restore", "console", "usage", "set_ip"}
    if action not in allowed:
        frappe.throw("Unknown VPS action")
    inst = frappe.get_doc("VPS Instance", instance)
    if inst.status == "Terminated":
        frappe.throw("Instance terminated")
    if action == "set_ip" and arg:
        inst.ipv4 = arg
        inst.save(ignore_permissions=True)
    if action == "console":
        return {"url": f"/vps/{instance}/console", "one_time": True}
    if action == "usage":
        return {"disk": 0, "bandwidth": 0}
    _audit(instance, action, f"vps-{action}:{instance}:{arg or ''}")
    return {"instance": instance, "action": action}
