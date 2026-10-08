"""Live Hetzner adapter tests. Transport is faked; no network happens."""

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.provisioning.hetzner import HetznerCloudAdapter


class FakeResp:
    def __init__(self, body, status_code=200):
        self._body = body
        self.status_code = status_code

    def json(self):
        return self._body


def ok(**extra):
    return FakeResp(extra)


class FakeTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        import json

        try:
            parsed = json.loads(body or "{}")
        except Exception:
            parsed = {}
        self.calls.append(
            {"method": method, "url": url, "auth": headers.get("Authorization", ""), "body": parsed}
        )
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item if isinstance(item, FakeResp) else FakeResp(item)


class TestHetznerLiveAdapter(IntegrationTestCase):
    def _server(self):
        name = frappe.db.get_value("Server", {"hostname": "hcloud-test.local"}, "name")
        if name:
            return name
        doc = frappe.get_doc(
            {
                "doctype": "Server",
                "hostname": "hcloud-test.local",
                "ip_address": "10.0.0.14",
                "api_username": "hcloud",
                "control_panel": "Custom",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        doc.set("api_secret", "htoken")
        doc.save(ignore_permissions=True)
        return doc.name

    def _service(self, server, vendor_ref="12345"):
        group = frappe.db.get_value("Product Group", {"group_name": "Hetz Group"}, "name")
        if not group:
            group = frappe.get_doc({"doctype": "Product Group", "group_name": "Hetz Group"}).insert().name
        plan = frappe.db.get_value("Hosting Plan", {"plan_name": "Hetz Plan"}, "name")
        if not plan:
            plan = frappe.get_doc(
                {
                    "doctype": "Hosting Plan",
                    "plan_name": "Hetz Plan",
                    "product_group": group,
                    "product_type": "Cloud",
                    "is_active": 1,
                }
            ).insert().name
        cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
        if not cust:
            cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
        return frappe.get_doc(
            {
                "doctype": "Service",
                "customer": cust,
                "hosting_plan": plan,
                "server": server,
                "svc_username": "hetzuser1",
                "primary_domain": "hetzuser1.test",
                "vendor_ref": vendor_ref,
                "status": "Pending",
            }
        ).insert(ignore_permissions=True).name

    def test_create_power_terminate(self):
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok(server={"id": 12345})])
            out = HetznerCloudAdapter().create_account(svc, password="Pw12345678!", transport=t)
            self.assertEqual(out["server_id"], 12345)
            self.assertTrue(t.calls[0]["url"].endswith("/servers"))
            self.assertTrue(t.calls[0]["auth"].startswith("Bearer "))
            self.assertEqual(t.calls[0]["body"]["image"], "ubuntu-24.04")

            t = FakeTransport([ok(action={"id": 1})])
            self.assertEqual(HetznerCloudAdapter().start(svc, transport=t)["action"], "start")
            self.assertIn("/servers/12345/actions/poweron", t.calls[0]["url"])

            t = FakeTransport([ok()])
            self.assertEqual(
                HetznerCloudAdapter().terminate_account(svc, transport=t)["terminated"],
                HetznerCloudAdapter()._service(svc).name,
            )
            self.assertEqual(t.calls[0]["method"], "DELETE")
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_rebuild_password_package_usage(self):
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok(action={"id": 2})])
            out = HetznerCloudAdapter().rebuild(svc, "ubuntu-24.04", password="Pw12345678!", transport=t)
            self.assertIn("/actions/rebuild", t.calls[0]["url"])

            t = FakeTransport([ok()])
            HetznerCloudAdapter().change_password(svc, "Pw99999999!", transport=t)
            self.assertIn("/actions/reset_password", t.calls[0]["url"])

            t = FakeTransport([ok()])
            HetznerCloudAdapter().change_package(svc, "cx32", transport=t)
            self.assertEqual(t.calls[0]["body"]["server_type"], "cx32")

            series = {"cpu": {"values": [[1, "0.5"]]}, "network.0.bandwidth.out": {"values": [[1, "100"]]}}
            t = FakeTransport([ok(metrics={"time_series": series})])
            out = HetznerCloudAdapter().get_usage(svc, transport=t)
            self.assertEqual(out["cpu"], "0.5")
            self.assertEqual(out["bandwidth"], "100")
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_reject_and_retry(self):
        server = self._server()
        t = FakeTransport([FakeResp({"error": {"message": "nope"}}, 401)])
        self.assertRaises(
            frappe.ValidationError, HetznerCloudAdapter().test_connection, server, transport=t
        )
        import requests

        t = FakeTransport([requests.ConnectionError("down"), ok(datacenters=[])])
        self.assertTrue(HetznerCloudAdapter().test_connection(server, transport=t)["ok"])
        self.assertEqual(len(t.calls), 2)
