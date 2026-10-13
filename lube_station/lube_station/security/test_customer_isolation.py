"""Cross-customer isolation: every customer-visible DocType leaks only own rows.

Regression for VPS-0157 leak (Customer B saw Customer A's instance via
frappe.client.get_list on VPS Instance). Covers Order, Cart, KYC,
Registered Domain, DNS Record, Saved Payment Method, VPS Instance +
my_vps / vps_control fail-closed on orphans.
"""

import uuid

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.portal import apis
from lube_station.lube_station.security.roles import ensure_roles


def _user_with_customer_role(prefix: str) -> str:
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    frappe.get_doc(
        {
            "doctype": "User",
            "email": email,
            "first_name": "Iso",
            "enabled": 1,
            "roles": [{"role": "Customer"}],
        }
    ).insert(ignore_permissions=True)
    return email


def _customer(prefix: str) -> tuple[str, str]:
    email = _user_with_customer_role(prefix)
    cust = frappe.get_doc(
        {"doctype": "Hosting Customer", "user": email, "status": "Active"}
    ).insert(ignore_permissions=True)
    return cust.name, email


class TestCustomerIsolation(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        ensure_roles()
        frappe.set_user("Administrator")

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def _seed_pair(self):
        cust_a, user_a = _customer("isoA")
        cust_b, user_b = _customer("isoB")
        order_a = frappe.get_doc(
            {"doctype": "Order", "customer": cust_a, "status": "Accepted"}
        ).insert(ignore_permissions=True).name
        order_b = frappe.get_doc(
            {"doctype": "Order", "customer": cust_b, "status": "Accepted"}
        ).insert(ignore_permissions=True).name
        group = frappe.get_doc(
            {"doctype": "Product Group", "group_name": f"ISO {uuid.uuid4().hex[:6]}"}
        ).insert(ignore_permissions=True)
        plan = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": f"ISO {uuid.uuid4().hex[:6]}",
                "product_group": group.name,
                "product_type": "VPS",
                "is_active": 1,
            }
        ).insert(ignore_permissions=True)
        cfg = frappe.get_doc(
            {"doctype": "VPS Configuration", "hosting_plan": plan.name}
        ).insert(ignore_permissions=True)
        inst_a = frappe.get_doc(
            {
                "doctype": "VPS Instance",
                "configuration": cfg.name,
                "order_ref": order_a,
                "image": "ubuntu-24.04",
                "location": "fsn1",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        inst_b = frappe.get_doc(
            {
                "doctype": "VPS Instance",
                "configuration": cfg.name,
                "order_ref": order_b,
                "image": "ubuntu-24.04",
                "location": "fsn1",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        dom_a = f"iso-a-{uuid.uuid4().hex[:8]}.example.com"
        dom_b = f"iso-b-{uuid.uuid4().hex[:8]}.example.com"
        frappe.get_doc(
            {"doctype": "Registered Domain", "domain_name": dom_a, "customer": cust_a}
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {"doctype": "Registered Domain", "domain_name": dom_b, "customer": cust_b}
        ).insert(ignore_permissions=True)
        dns_a = frappe.get_doc(
            {
                "doctype": "DNS Record",
                "domain": dom_a,
                "record_type": "A",
                "hostname": "@",
                "record_value": "203.0.113.10",
            }
        ).insert(ignore_permissions=True)
        dns_b = frappe.get_doc(
            {
                "doctype": "DNS Record",
                "domain": dom_b,
                "record_type": "A",
                "hostname": "@",
                "record_value": "203.0.113.11",
            }
        ).insert(ignore_permissions=True)
        cart_a = frappe.get_doc(
            {"doctype": "Cart", "customer": cust_a}
        ).insert(ignore_permissions=True)
        cart_b = frappe.get_doc(
            {"doctype": "Cart", "customer": cust_b}
        ).insert(ignore_permissions=True)
        kyc_a = frappe.get_doc(
            {"doctype": "Customer KYC Verification", "customer": cust_a}
        ).insert(ignore_permissions=True)
        kyc_b = frappe.get_doc(
            {"doctype": "Customer KYC Verification", "customer": cust_b}
        ).insert(ignore_permissions=True)
        pm_a = frappe.get_doc(
            {
                "doctype": "Saved Payment Method",
                "customer": cust_a,
                "gateway": "Stripe",
                "token": "tok_a",
            }
        ).insert(ignore_permissions=True)
        pm_b = frappe.get_doc(
            {
                "doctype": "Saved Payment Method",
                "customer": cust_b,
                "gateway": "Stripe",
                "token": "tok_b",
            }
        ).insert(ignore_permissions=True)
        return {
            "a": cust_a,
            "b": cust_b,
            "user_a": user_a,
            "user_b": user_b,
            "order_a": order_a,
            "order_b": order_b,
            "inst_a": inst_a.name,
            "inst_b": inst_b.name,
            "dom_a": dom_a,
            "dom_b": dom_b,
            "dns_a": dns_a.name,
            "dns_b": dns_b.name,
            "cart_a": cart_a.name,
            "cart_b": cart_b.name,
            "kyc_a": kyc_a.name,
            "kyc_b": kyc_b.name,
            "pm_a": pm_a.name,
            "pm_b": pm_b.name,
        }

    def _assert_own_only(self, doctype, own, other, user):
        frappe.set_user(user)
        names = frappe.get_list(doctype, pluck="name")
        self.assertIn(own, names)
        self.assertNotIn(other, names)
        # Direct read of the other's row must fail (client path enforces
        # has_permission hooks; server-side get_doc intentionally bypasses).
        self.assertFalse(frappe.has_permission(doctype, "read", other))
        from frappe.client import get as client_get

        with self.assertRaises(frappe.PermissionError):
            client_get(doctype, other)

    def test_get_list_isolation(self):
        s = self._seed_pair()
        self._assert_own_only("Order", s["order_a"], s["order_b"], s["user_a"])
        self._assert_own_only("Order", s["order_b"], s["order_a"], s["user_b"])
        self._assert_own_only("VPS Instance", s["inst_a"], s["inst_b"], s["user_a"])
        self._assert_own_only("VPS Instance", s["inst_b"], s["inst_a"], s["user_b"])
        self._assert_own_only(
            "Registered Domain", s["dom_a"], s["dom_b"], s["user_a"]
        )
        self._assert_own_only("DNS Record", s["dns_a"], s["dns_b"], s["user_a"])
        self._assert_own_only("DNS Record", s["dns_b"], s["dns_a"], s["user_b"])
        self._assert_own_only("Cart", s["cart_a"], s["cart_b"], s["user_a"])
        self._assert_own_only(
            "Customer KYC Verification", s["kyc_a"], s["kyc_b"], s["user_a"]
        )
        self._assert_own_only(
            "Saved Payment Method", s["pm_a"], s["pm_b"], s["user_a"]
        )
        self._assert_own_only(
            "Saved Payment Method", s["pm_b"], s["pm_a"], s["user_b"]
        )

    def test_my_vps_and_control_isolation(self):
        s = self._seed_pair()
        frappe.set_user(s["user_a"])
        mine = [r["name"] for r in apis.my_vps()]
        self.assertIn(s["inst_a"], mine)
        self.assertNotIn(s["inst_b"], mine)
        # Cross-customer control denied.
        with self.assertRaises(frappe.PermissionError):
            apis.vps_control(s["inst_b"], "reboot")
        with self.assertRaises(frappe.PermissionError):
            apis.vps_snapshots(s["inst_b"])
        frappe.set_user(s["user_b"])
        mine_b = [r["name"] for r in apis.my_vps()]
        self.assertIn(s["inst_b"], mine_b)
        self.assertNotIn(s["inst_a"], mine_b)

    def test_dedicated_isolation(self):
        from lube_station.lube_station.provisioning import dedicated as ded

        s = self._seed_pair()
        frappe.set_user("Administrator")
        group = frappe.get_doc(
            {"doctype": "Product Group", "group_name": f"DD {uuid.uuid4().hex[:6]}"}
        ).insert(ignore_permissions=True)
        plan = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": f"DD {uuid.uuid4().hex[:6]}",
                "product_group": group.name,
                "product_type": "Dedicated Server",
                "is_active": 1,
            }
        ).insert(ignore_permissions=True)
        svc_a = frappe.get_doc(
            {
                "doctype": "Service",
                "customer": s["a"],
                "hosting_plan": plan.name,
                "status": "Active",
                "recurring_amount": 100,
            }
        ).insert(ignore_permissions=True)
        svc_b = frappe.get_doc(
            {
                "doctype": "Service",
                "customer": s["b"],
                "hosting_plan": plan.name,
                "status": "Active",
                "recurring_amount": 100,
            }
        ).insert(ignore_permissions=True)
        inv_a = frappe.get_doc(
            {
                "doctype": "Dedicated Server Inventory",
                "asset_id": f"AST-A-{uuid.uuid4().hex[:6]}",
                "cpu": "Xeon",
                "ram_gb": 64,
                "location": "fsn1",
                "status": "Assigned",
                "assigned_service": svc_a.name,
            }
        ).insert(ignore_permissions=True)
        inv_b = frappe.get_doc(
            {
                "doctype": "Dedicated Server Inventory",
                "asset_id": f"AST-B-{uuid.uuid4().hex[:6]}",
                "cpu": "Xeon",
                "ram_gb": 64,
                "location": "fsn1",
                "status": "Assigned",
                "assigned_service": svc_b.name,
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(s["user_a"])
        mine = [r["name"] for r in apis.my_dedicated()]
        self.assertIn(inv_a.name, mine)
        self.assertNotIn(inv_b.name, mine)
        with self.assertRaises(frappe.PermissionError):
            apis.dedicated_control(inv_b.name, "install_os")
        # Direct provisioning endpoints: customers blocked entirely.
        with self.assertRaises(frappe.PermissionError):
            ded.provision_step(inv_b.name, "install_os")
        with self.assertRaises(frappe.PermissionError):
            ded.reserve_inventory("whatever", "lease-x")
        with self.assertRaises(frappe.PermissionError):
            ded.release_inventory(inv_a.name, wipe_confirmed=True)
        # Owner path still works through the portal guard.
        out = apis.dedicated_control(inv_a.name, "install_os")
        self.assertTrue(out["queued"])

    def test_domain_isolation(self):
        from lube_station.lube_domains.doctype.registered_domain import (
            registered_domain as rd,
        )

        s = self._seed_pair()
        frappe.set_user(s["user_a"])
        # Renew / nameserver changes on someone else's domain denied.
        with self.assertRaises(frappe.PermissionError):
            rd.renew_domain(s["dom_b"])
        with self.assertRaises(frappe.PermissionError):
            rd.update_nameservers(s["dom_b"], ["ns1.evil.test"])
        # register/transfer pinned to own customer.
        with self.assertRaises(frappe.PermissionError):
            rd.register_domain("evil.example.com", customer=s["b"])
        with self.assertRaises(frappe.PermissionError):
            rd.transfer_domain("evil2.example.com", "epp", customer=s["b"])
        # Portal readers stay scoped.
        self.assertEqual(
            [d["domain_name"] for d in apis.my_domains()], [s["dom_a"]]
        )
        with self.assertRaises(frappe.PermissionError):
            apis.dns_list(s["dom_b"])

    def test_download_entitlement_self_only(self):
        from lube_station.lube_catalog.doctype.downloadable_asset import (
            downloadable_asset as da,
        )

        s = self._seed_pair()
        frappe.set_user("Administrator")
        group = frappe.get_doc(
            {"doctype": "Product Group", "group_name": f"DL {uuid.uuid4().hex[:6]}"}
        ).insert(ignore_permissions=True)
        plan = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": f"DL {uuid.uuid4().hex[:6]}",
                "product_group": group.name,
                "product_type": "Shared Hosting",
                "is_active": 1,
            }
        ).insert(ignore_permissions=True)
        # Only B holds an Active service on this plan.
        frappe.get_doc(
            {
                "doctype": "Service",
                "customer": s["b"],
                "hosting_plan": plan.name,
                "status": "Active",
                "recurring_amount": 10,
            }
        ).insert(ignore_permissions=True)
        asset = frappe.get_doc(
            {
                "doctype": "Downloadable Asset",
                "title": f"DL {uuid.uuid4().hex[:6]}",
                "storage_type": "Remote URL",
                "remote_url": "https://example.com/f.iso",
                "access_policy": "Active Service",
                "allowed_products": [{"hosting_plan": plan.name}],
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(s["user_a"])
        self.assertFalse(da.check_entitlement(asset.name)["allowed"])
        # Probing another user's entitlement must not flip to True.
        self.assertFalse(da.check_entitlement(asset.name, s["user_b"])["allowed"])
        frappe.set_user(s["user_b"])
        self.assertTrue(da.check_entitlement(asset.name)["allowed"])
        # Portal download list respects it.
        frappe.set_user(s["user_a"])
        self.assertNotIn(asset.name, [a["name"] for a in apis.downloads()])
        frappe.set_user(s["user_b"])
        self.assertIn(asset.name, [a["name"] for a in apis.downloads()])

    def test_addon_isolation(self):
        s = self._seed_pair()
        frappe.set_user("Administrator")
        group = frappe.get_doc(
            {"doctype": "Product Group", "group_name": f"AO {uuid.uuid4().hex[:6]}"}
        ).insert(ignore_permissions=True)
        plan = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": f"AO {uuid.uuid4().hex[:6]}",
                "product_group": group.name,
                "product_type": "Backup Addon",
                "is_active": 1,
            }
        ).insert(ignore_permissions=True)
        parent_a = frappe.get_doc(
            {
                "doctype": "Service",
                "customer": s["a"],
                "hosting_plan": plan.name,
                "status": "Active",
                "recurring_amount": 10,
            }
        ).insert(ignore_permissions=True)
        child_a = frappe.get_doc(
            {
                "doctype": "Service",
                "customer": s["a"],
                "hosting_plan": plan.name,
                "status": "Active",
                "recurring_amount": 5,
                "parent_service": parent_a.name,
            }
        ).insert(ignore_permissions=True)
        parent_b = frappe.get_doc(
            {
                "doctype": "Service",
                "customer": s["b"],
                "hosting_plan": plan.name,
                "status": "Active",
                "recurring_amount": 10,
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(s["user_a"])
        detail = apis.my_service_detail(parent_a.name)
        addon_names = [a["name"] for a in detail["addons"]]
        self.assertIn(child_a.name, addon_names)
        self.assertNotIn(parent_b.name, addon_names)
        # Other customer's service detail denied outright.
        with self.assertRaises(frappe.PermissionError):
            apis.my_service_detail(parent_b.name)
        # Add-on cart line cannot attach to someone else's parent.
        cart = apis.cart_current()
        with self.assertRaises(frappe.PermissionError):
            apis.cart_add(
                plan.name, "Monthly", parent_service=parent_b.name, cart=cart["cart"]
            )

    def test_billing_fulfillment_isolation(self):
        from lube_station.lube_provisioning.doctype.service import service as svcmod

        s = self._seed_pair()
        frappe.set_user("Administrator")
        group = frappe.get_doc(
            {"doctype": "Product Group", "group_name": f"BL {uuid.uuid4().hex[:6]}"}
        ).insert(ignore_permissions=True)
        plan = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": f"BL {uuid.uuid4().hex[:6]}",
                "product_group": group.name,
                "product_type": "Shared Hosting",
                "is_active": 1,
            }
        ).insert(ignore_permissions=True)
        frappe.get_doc(
            {
                "doctype": "Plan Pricing",
                "hosting_plan": plan.name,
                "billing_cycle": "Monthly",
                "recurring_amount": 50,
            }
        ).insert(ignore_permissions=True)
        cart = frappe.get_doc(
            {"doctype": "Cart", "customer": s["a"]}
        ).insert(ignore_permissions=True)
        cart.append(
            "items",
            {
                "item_type": "Hosting Plan",
                "hosting_plan": plan.name,
                "billing_cycle": "Monthly",
                "quantity": 1,
            },
        )
        cart.save(ignore_permissions=True)
        from lube_station.lube_customers.doctype.order.order import place_order

        order = place_order(cart.name, s["a"])["order"]
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": s["a"],
                "order_ref": order,
                "invoice_items": [{"description": "t", "amount": 50}],
                "status": "Paid",
            }
        ).insert(ignore_permissions=True)
        # Stranger cannot create services, fire paid-fulfillment, or run dunning.
        frappe.set_user(s["user_b"])
        with self.assertRaises(frappe.PermissionError):
            svcmod.create_from_order(order)
        with self.assertRaises(frappe.PermissionError):
            svcmod.on_invoice_paid(inv.name)
        with self.assertRaises(frappe.PermissionError):
            svcmod.apply_dunning(inv.name)
        # Owner's own paid invoice still fulfills (idempotent re-fire allowed).
        frappe.set_user("Administrator")
        frappe.db.set_value("Hosting Customer", s["a"], "kyc_status", "Verified")
        made = svcmod.create_from_order(order)["services"]
        self.assertTrue(made)
        frappe.set_user(s["user_a"])
        out = svcmod.on_invoice_paid(inv.name)
        self.assertIn("action", out)
        self.assertEqual(
            frappe.db.get_value("Service", made[0], "status"), "Active"
        )

    def test_orphan_vps_fail_closed(self):
        s = self._seed_pair()
        frappe.set_user("Administrator")
        group = frappe.get_doc(
            {"doctype": "Product Group", "group_name": f"ORP {uuid.uuid4().hex[:6]}"}
        ).insert(ignore_permissions=True)
        plan = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": f"ORP {uuid.uuid4().hex[:6]}",
                "product_group": group.name,
                "product_type": "VPS",
                "is_active": 1,
            }
        ).insert(ignore_permissions=True)
        cfg = frappe.get_doc(
            {"doctype": "VPS Configuration", "hosting_plan": plan.name}
        ).insert(ignore_permissions=True)
        orphan = frappe.get_doc(
            {
                "doctype": "VPS Instance",
                # No order_ref: must never be customer-visible or controllable.
                "configuration": cfg.name,
                "image": "ubuntu-24.04",
                "location": "fsn1",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        frappe.set_user(s["user_a"])
        self.assertNotIn(orphan.name, frappe.get_list("VPS Instance", pluck="name"))
        self.assertNotIn(orphan.name, [r["name"] for r in apis.my_vps()])
        with self.assertRaises(frappe.PermissionError):
            apis.vps_control(orphan.name, "reboot")
        with self.assertRaises(frappe.PermissionError):
            apis.vps_snapshots(orphan.name)
