import uuid
from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.portal import apis


def _make_customer():
    email = f"actions-{uuid.uuid4().hex[:10]}@test.com"
    user = frappe.get_doc(
        {"doctype": "User", "email": email, "first_name": "Actions", "enabled": 1}
    ).insert(ignore_permissions=True)
    cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert(
        ignore_permissions=True
    )
    return cust.name, user.name


def _plan(product_type="Shared Hosting", **kw):
    group = frappe.get_doc({"doctype": "Product Group", "group_name": f"AG {uuid.uuid4().hex[:6]}"}).insert()
    args = {
        "doctype": "Hosting Plan",
        "plan_name": f"AP {uuid.uuid4().hex[:6]}",
        "product_group": group.name,
        "product_type": product_type,
        "is_active": 1,
    }
    args.update(kw)
    return frappe.get_doc(args).insert()


def _price(plan, cycle="Monthly", amount=10):
    return frappe.get_doc(
        {"doctype": "Plan Pricing", "hosting_plan": plan, "billing_cycle": cycle, "recurring_amount": amount}
    ).insert()


class FakeAdapter:
    def change_password(self, service, password):
        return {"changed": service}

    def get_client_area(self, service):
        return {"panels": [], "buttons": [{"key": "panel", "label": "Open Panel", "kind": "link", "url": "https://panel.test:2083"}]}


class TestServiceActions(IntegrationTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def _cpanel_service(self, cust_name, with_user=True, product_type="Shared Hosting"):
        server = frappe.get_doc(
            {
                "doctype": "Server",
                "hostname": f"srv-{uuid.uuid4().hex[:6]}.test",
                "ip_address": "203.0.113.10",
                "control_panel": "cPanel / WHM",
                **({"api_username": "root"} if with_user else {}),
            }
        ).insert()
        module = frappe.get_doc(
            {
                "doctype": "Provisioning Module",
                "module_name": f"mod-{uuid.uuid4().hex[:6]}",
                "control_panel": "cPanel / WHM",
                "class_path": "lube_station.lube_station.adapters.provisioning.cpanel.CpanelWhmAdapter",
            }
        ).insert()
        plan = _plan(product_type=product_type, provisioning_module=module.name)
        _price(plan.name)
        svc = frappe.get_doc(
            {
                "doctype": "Service",
                "customer": cust_name,
                "hosting_plan": plan.name,
                "server": server.name,
                "svc_username": "acct1",
                "status": "Active",
                "recurring_amount": 10,
            }
        ).insert()
        return svc, plan, server

    def test_panel_url_and_client_area_buttons(self):
        cust_name, user_name = _make_customer()
        svc, _plan_doc, _server = self._cpanel_service(cust_name)
        frappe.set_user(user_name)
        detail = apis.my_service_detail(svc.name)
        self.assertEqual(detail["panel_url"], "https://203.0.113.10:2083")
        dumped = frappe.as_json(detail)
        self.assertNotIn("api_secret", dumped.lower())
        buttons = detail["management"]["buttons"]
        self.assertTrue(any(b["key"] == "panel" and b["kind"] == "link" for b in buttons))
        self.assertTrue(any(b["key"] == "webmail" for b in buttons))
        # Password needs live API creds: capability off without them... but api_username set.
        self.assertTrue(detail["capabilities"]["can_panel"])

    def test_change_password_happy_path_never_stores_secret(self):
        cust_name, user_name = _make_customer()
        svc, _plan_doc, _server = self._cpanel_service(cust_name)
        frappe.set_user(user_name)
        with mock.patch.object(apis, "_adapter_for_plan", return_value=FakeAdapter()):
            out = apis.change_service_password(svc.name, "N3w-portal-pass")
        self.assertTrue(out["changed"])
        comments = frappe.get_all(
            "Comment", {"reference_doctype": "Service", "reference_name": svc.name}, ["content"]
        )
        self.assertTrue(comments)
        for c in comments:
            self.assertNotIn("N3w-portal-pass", c["content"] or "")

    def test_change_password_gates(self):
        cust_name, user_name = _make_customer()
        svc, _plan_doc, _server = self._cpanel_service(cust_name)
        frappe.set_user(user_name)
        with mock.patch.object(apis, "_adapter_for_plan", return_value=FakeAdapter()):
            self.assertRaises(frappe.ValidationError, apis.change_service_password, svc.name, "short1")
            self.assertRaises(frappe.ValidationError, apis.change_service_password, svc.name, "longbutnodigits")
        # Inactive service rejected before touching the module.
        frappe.set_user("Administrator")
        svc.status = "Suspended"
        svc.save(ignore_permissions=True)
        frappe.set_user(user_name)
        with mock.patch.object(apis, "_adapter_for_plan", return_value=FakeAdapter()):
            self.assertRaises(frappe.ValidationError, apis.change_service_password, svc.name, "N3w-portal-pass")
        # Unsupported product (no module) rejected.
        frappe.set_user("Administrator")
        plan2 = _plan()
        _price(plan2.name)
        svc2 = frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": plan2.name, "status": "Active", "recurring_amount": 5}
        ).insert()
        frappe.set_user(user_name)
        self.assertRaises(frappe.ValidationError, apis.change_service_password, svc2.name, "N3w-portal-pass")

    def test_change_password_cross_customer_denied(self):
        cust_name, _user = _make_customer()
        svc, _plan_doc, _server = self._cpanel_service(cust_name)
        _other_cust, other_user = _make_customer()
        frappe.set_user(other_user)
        with mock.patch.object(apis, "_adapter_for_plan", return_value=FakeAdapter()):
            self.assertRaises(frappe.PermissionError, apis.change_service_password, svc.name, "N3w-portal-pass")

    def test_cancellation_happy_path_and_duplicate(self):
        cust_name, user_name = _make_customer()
        plan = _plan()
        _price(plan.name)
        svc = frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 5}
        ).insert()
        frappe.db.set_single_value("Lube Station Settings", "show_cancellation_link", 1)
        frappe.set_user(user_name)
        detail = apis.my_service_detail(svc.name)
        self.assertTrue(detail["capabilities"]["can_cancel"])
        # Guards: short reason, wrong confirm, missing ack all rejected.
        self.assertRaises(frappe.ValidationError, apis.request_cancellation, svc.name, "short", "End of Billing Cycle", svc.name, True)
        self.assertRaises(frappe.ValidationError, apis.request_cancellation, svc.name, "Moving provider now", "End of Billing Cycle", "WRONG", True)
        self.assertRaises(frappe.ValidationError, apis.request_cancellation, svc.name, "Moving provider now", "End of Billing Cycle", svc.name, False)
        out = apis.request_cancellation(svc.name, "Moving provider now", "End of Billing Cycle", svc.name, True)
        self.assertTrue(out["requested"])
        self.assertFalse(out["terminated"])
        self.assertEqual(frappe.db.get_value("Service", svc.name, "cancellation_mode"), "End of Billing Cycle")
        # Status stays Active until end of cycle; duplicate rejected.
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Active")
        self.assertRaises(frappe.ValidationError, apis.request_cancellation, svc.name, "Moving provider now", "Immediate", svc.name, True)
        # Withdraw works while scheduled.
        frappe.set_user(user_name)
        self.assertTrue(apis.withdraw_cancellation(svc.name)["withdrawn"])
        self.assertEqual(frappe.db.get_value("Service", svc.name, "cancellation_requested"), 0)

    def test_cancellation_immediate_auto_terminates(self):
        cust_name, user_name = _make_customer()
        plan = _plan()
        _price(plan.name)
        svc = frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 5}
        ).insert()
        frappe.db.set_single_value("Lube Station Settings", "show_cancellation_link", 1)
        frappe.set_user(user_name)
        out = apis.request_cancellation(svc.name, "Closing project now", "Immediate", svc.name, True)
        self.assertTrue(out["terminated"])
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Terminated")

    def test_scheduled_cancellation_auto_terminates_past_due(self):
        from frappe.utils import add_days, today

        cust_name, user_name = _make_customer()
        plan = _plan()
        _price(plan.name)
        svc = frappe.get_doc(
            {
                "doctype": "Service",
                "customer": cust_name,
                "hosting_plan": plan.name,
                "status": "Active",
                "recurring_amount": 5,
                "next_due_date": add_days(today(), -1),
            }
        ).insert()
        frappe.db.set_single_value("Lube Station Settings", "show_cancellation_link", 1)
        frappe.set_user(user_name)
        apis.request_cancellation(svc.name, "No longer needed here", "End of Billing Cycle", svc.name, True)
        frappe.set_user("Administrator")
        done = apis.process_scheduled_cancellations()
        self.assertIn(svc.name, done["terminated"])
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Terminated")

    def test_cancellation_disabled_by_setting(self):
        cust_name, user_name = _make_customer()
        plan = _plan()
        _price(plan.name)
        svc = frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 5}
        ).insert()
        frappe.db.set_single_value("Lube Station Settings", "show_cancellation_link", 0)
        frappe.set_user(user_name)
        detail = apis.my_service_detail(svc.name)
        self.assertFalse(detail["capabilities"]["can_cancel"])
        self.assertRaises(frappe.ValidationError, apis.request_cancellation, svc.name, "Moving provider now", "Immediate", svc.name, True)

    def test_upgrade_options_and_request(self):
        cust_name, user_name = _make_customer()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"UG {uuid.uuid4().hex[:6]}"}).insert()
        small = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"US {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        big = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"UB {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        _price(small.name, amount=10)
        _price(big.name, amount=25)
        svc = frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": small.name, "billing_cycle": "Monthly", "status": "Active", "recurring_amount": 10}
        ).insert()
        frappe.set_user(user_name)
        options = apis.upgrade_options(svc.name)
        self.assertIn(big.name, [o["plan"] for o in options])
        self.assertNotIn(small.name, [o["plan"] for o in options])
        detail = apis.my_service_detail(svc.name)
        self.assertTrue(detail["capabilities"]["can_upgrade"])
        quote = apis.upgrade_quote(svc.name, big.name)
        self.assertGreaterEqual(quote["total_due"], 0)
        self.assertTrue(quote["payment_required"] or quote["total_due"] <= 0)
        out = apis.request_upgrade(svc.name, big.name)
        # Positive prorated balance -> unpaid upgrade invoice, no swap yet.
        self.assertTrue(out.get("payment_required"))
        self.assertTrue(out.get("invoice"))
        inv = frappe.get_doc("Hosting Invoice", out["invoice"])
        self.assertEqual(inv.status, "Unpaid")
        self.assertEqual(frappe.db.get_value("Service", svc.name, "hosting_plan"), small.name)
        # Paying the balance swaps the plan automatically.
        inv.status = "Paid"
        inv.save(ignore_permissions=True)
        from lube_station.lube_provisioning.doctype.service.service import on_invoice_paid

        frappe.set_user("Administrator")
        on_invoice_paid(inv.name)
        self.assertEqual(frappe.db.get_value("Service", svc.name, "hosting_plan"), big.name)
        frappe.set_user(user_name)
        self.assertRaises(frappe.ValidationError, apis.request_upgrade, svc.name, big.name)

    def test_downgrade_no_balance_swaps_immediately(self):
        cust_name, user_name = _make_customer()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"DG {uuid.uuid4().hex[:6]}"}).insert()
        cheap = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"DC {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        pricey = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"DP {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        _price(cheap.name, amount=5)
        _price(pricey.name, amount=30)
        svc = frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": pricey.name, "billing_cycle": "Monthly", "status": "Active", "recurring_amount": 30}
        ).insert()
        frappe.set_user(user_name)
        out = apis.request_upgrade(svc.name, cheap.name)
        self.assertTrue(out.get("applied"))
        self.assertEqual(frappe.db.get_value("Service", svc.name, "hosting_plan"), cheap.name)

    def test_usage_section_links_snapshots_and_limits(self):
        from lube_station.lube_station.usage.collect import collect_usage

        cust_name, user_name = _make_customer()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"UU {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"UP {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "VPS", "is_active": 1}).insert()
        _price(plan.name)
        frappe.get_doc({"doctype": "VPS Configuration", "hosting_plan": plan.name, "cpu_cores": 2, "ram_mb": 2048, "storage_gb": 40, "bandwidth_gb": 500}).insert()
        svc = frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "billing_cycle": "Monthly", "status": "Active", "recurring_amount": 30}
        ).insert()
        collect_usage(svc.name, disk=5, bandwidth=12)
        frappe.set_user(user_name)
        detail = apis.my_service_detail(svc.name)
        self.assertEqual(detail["usage"]["limits"], {"disk": 40, "bandwidth": 500})
        self.assertEqual(len(detail["usage"]["snapshots"]), 1)
        snap = detail["usage"]["snapshots"][0]
        self.assertEqual(snap["disk_used"], 5)
        self.assertEqual(snap["bandwidth_used"], 12)

    def test_vps_snapshot_capability_follows_backup_flag(self):
        cust_name, user_name = _make_customer()
        plan = _plan(product_type="VPS")
        _price(plan.name)
        order = frappe.get_doc({"doctype": "Order", "customer": cust_name, "status": "Accepted"}).insert(ignore_permissions=True)
        cfg = frappe.get_doc({"doctype": "VPS Configuration", "hosting_plan": plan.name, "backup_enabled": 1}).insert()
        inst = frappe.get_doc({"doctype": "VPS Instance", "configuration": cfg.name, "order_ref": order.name, "image": "ubuntu-24.04", "location": "fsn1", "status": "Active"}).insert()
        svc = frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "order_ref": order.name, "status": "Active", "recurring_amount": 20}
        ).insert()
        frappe.set_user(user_name)
        detail = apis.my_service_detail(svc.name)
        self.assertTrue(detail["capabilities"]["can_vps_rebuild"])
        self.assertTrue(detail["capabilities"]["can_vps_snapshot"])
        out = apis.vps_control(inst.name, "snapshot")
        self.assertEqual(out["action"], "snapshot")

    def _dedicated_service(self, cust_name):
        inv = frappe.get_doc(
            {"doctype": "Dedicated Server Inventory", "asset_id": f"AST-{uuid.uuid4().hex[:6]}", "cpu": "Xeon", "ram_gb": 64, "location": "fsn1", "status": "Available"}
        ).insert()
        plan = _plan(product_type="Dedicated Server")
        _price(plan.name)
        svc = frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 100}
        ).insert()
        inv.status = "Assigned"
        inv.assigned_service = svc.name
        inv.save(ignore_permissions=True)
        return inv, svc

    def test_dedicated_control_happy_path_and_rdns(self):
        cust_name, user_name = _make_customer()
        inv, svc = self._dedicated_service(cust_name)
        frappe.set_user(user_name)
        detail = apis.my_service_detail(svc.name)
        self.assertTrue(detail["capabilities"]["can_dedicated_control"])
        out = apis.dedicated_control(inv.name, "install_os")
        self.assertTrue(out["queued"])
        out = apis.dedicated_control(inv.name, "rdns", "host.example.com")
        self.assertEqual(out["hostname"], "host.example.com")
        self.assertRaises(frappe.ValidationError, apis.dedicated_control, inv.name, "rdns", "not a hostname!!")

    def test_dedicated_control_gates(self):
        cust_name, _user = _make_customer()
        inv, svc = self._dedicated_service(cust_name)
        # Credentials step stays Admin Only: not reachable from portal.
        _other_cust, other_user = _make_customer()
        frappe.set_user(other_user)
        self.assertRaises(frappe.PermissionError, apis.dedicated_control, inv.name, "panel")
        owner = frappe.db.get_value("Hosting Customer", cust_name, "user")
        frappe.set_user(owner)
        self.assertRaises(frappe.ValidationError, apis.dedicated_control, inv.name, "credentials")
        self.assertRaises(frappe.ValidationError, apis.dedicated_control, inv.name, "nope")
        # Inactive service rejected.
        frappe.set_user("Administrator")
        svc.status = "Suspended"
        svc.save(ignore_permissions=True)
        frappe.set_user(owner)
        self.assertRaises(frappe.ValidationError, apis.dedicated_control, inv.name, "panel")

    def test_snapshot_registry_and_restore_picker(self):
        cust_name, user_name = _make_customer()
        plan = _plan(product_type="VPS")
        _price(plan.name)
        order = frappe.get_doc({"doctype": "Order", "customer": cust_name, "status": "Accepted"}).insert(ignore_permissions=True)
        cfg = frappe.get_doc({"doctype": "VPS Configuration", "hosting_plan": plan.name, "backup_enabled": 1}).insert()
        inst = frappe.get_doc({"doctype": "VPS Instance", "configuration": cfg.name, "order_ref": order.name, "image": "ubuntu-24.04", "location": "fsn1", "status": "Active"}).insert()
        frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "order_ref": order.name, "status": "Active", "recurring_amount": 20}
        ).insert()
        frappe.set_user(user_name)
        # Snapshot registers a restore point.
        apis.vps_control(inst.name, "snapshot")
        snaps = apis.vps_snapshots(inst.name)
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0]["status"], "Available")
        # Restore happy path marks Restoring + trails a comment.
        out = apis.vps_restore(inst.name, snaps[0]["name"])
        self.assertEqual(out["snapshot"], snaps[0]["name"])
        self.assertEqual(frappe.db.get_value("VPS Snapshot", snaps[0]["name"], "status"), "Restoring")
        # A snapshot from another instance is rejected.
        frappe.set_user("Administrator")
        inst2 = frappe.get_doc({"doctype": "VPS Instance", "configuration": cfg.name, "order_ref": order.name, "image": "debian-12", "location": "fsn1", "status": "Active"}).insert()
        frappe.set_user(user_name)
        self.assertRaises(frappe.ValidationError, apis.vps_restore, inst2.name, snaps[0]["name"])
        # Strangers cannot list or restore.
        _other_cust, other_user = _make_customer()
        frappe.set_user(other_user)
        self.assertRaises(frappe.PermissionError, apis.vps_snapshots, inst.name)
        self.assertRaises(frappe.PermissionError, apis.vps_restore, inst.name, snaps[0]["name"])

    def test_rescue_mode_vps_and_dedicated(self):
        cust_name, user_name = _make_customer()
        plan = _plan(product_type="VPS")
        _price(plan.name)
        order = frappe.get_doc({"doctype": "Order", "customer": cust_name, "status": "Accepted"}).insert(ignore_permissions=True)
        cfg = frappe.get_doc({"doctype": "VPS Configuration", "hosting_plan": plan.name}).insert()
        inst = frappe.get_doc({"doctype": "VPS Instance", "configuration": cfg.name, "order_ref": order.name, "image": "ubuntu-24.04", "location": "fsn1", "status": "Active"}).insert()
        frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "order_ref": order.name, "status": "Active", "recurring_amount": 20}
        ).insert()
        frappe.set_user(user_name)
        detail = apis.my_service_detail(frappe.db.get_value("Service", {"order_ref": order.name}, "name"))
        self.assertTrue(detail["capabilities"]["can_vps_rescue"])
        out = apis.vps_control(inst.name, "rescue")
        self.assertEqual(out["action"], "rescue")
        # Terminated instances stay out of rescue.
        frappe.set_user("Administrator")
        inst.status = "Terminated"
        inst.save(ignore_permissions=True)
        frappe.set_user(user_name)
        self.assertRaises(frappe.ValidationError, apis.vps_control, inst.name, "rescue")

    def test_rescue_mode_dedicated_queued(self):
        cust_name, user_name = _make_customer()
        inv, _svc = self._dedicated_service(cust_name)
        frappe.set_user(user_name)
        out = apis.dedicated_control(inv.name, "rescue")
        self.assertTrue(out["queued"])

    def test_reseller_gets_whm_button_shared_does_not(self):
        cust_name, user_name = _make_customer()
        svc, _plan_doc, _server = self._cpanel_service(cust_name, product_type="Reseller")
        frappe.set_user(user_name)
        detail = apis.my_service_detail(svc.name)
        keys = [b["key"] for b in detail["management"]["buttons"]]
        self.assertIn("whm", keys)
        self.assertIn("panel", keys)
        self.assertIn("webmail", keys)
        frappe.set_user("Administrator")
        cust2, user2 = _make_customer()
        svc2, _p2, _s2 = self._cpanel_service(cust2)
        frappe.set_user(user2)
        detail2 = apis.my_service_detail(svc2.name)
        self.assertNotIn("whm", [b["key"] for b in detail2["management"]["buttons"]])


class FakeSsoAdapter:
    def create_sso_session(self, service):
        return {"url": f"https://panel.test:2083/cpsess{service}/login/?session=one-time"}

    def get_client_area(self, service):
        return {"panels": [], "buttons": []}


class TestPanelSso(IntegrationTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def _sso_service(self, cust_name, status="Active", with_user=True):
        server = frappe.get_doc(
            {
                "doctype": "Server",
                "hostname": f"sso-{uuid.uuid4().hex[:6]}.test",
                "ip_address": "203.0.113.20",
                "control_panel": "cPanel / WHM",
                **({"api_username": "root"} if with_user else {}),
            }
        ).insert()
        module = frappe.get_doc(
            {
                "doctype": "Provisioning Module",
                "module_name": f"ssomod-{uuid.uuid4().hex[:6]}",
                "control_panel": "cPanel / WHM",
                "class_path": "lube_station.lube_station.adapters.provisioning.cpanel.CpanelWhmAdapter",
            }
        ).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"SSG {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": f"SSP {uuid.uuid4().hex[:6]}",
                "product_group": group.name,
                "product_type": "Shared Hosting",
                "is_active": 1,
                "provisioning_module": module.name,
            }
        ).insert()
        svc = frappe.get_doc(
            {
                "doctype": "Service",
                "customer": cust_name,
                "hosting_plan": plan.name,
                "server": server.name,
                "svc_username": "ssouser1",
                "status": status,
                "recurring_amount": 10,
            }
        ).insert()
        return svc

    def test_can_sso_flag(self):
        cust_name, user_name = _make_customer()
        svc = self._sso_service(cust_name)
        frappe.set_user(user_name)
        detail = apis.my_service_detail(svc.name)
        self.assertTrue(detail["capabilities"]["can_sso"])
        self.assertTrue(detail["capabilities"]["can_panel"])

    def test_can_sso_off_when_suspended_or_no_creds(self):
        cust_name, user_name = _make_customer()
        svc = self._sso_service(cust_name, status="Suspended")
        frappe.set_user(user_name)
        self.assertFalse(apis.my_service_detail(svc.name)["capabilities"]["can_sso"])
        frappe.set_user("Administrator")
        cust2, user2 = _make_customer()
        svc2 = self._sso_service(cust2, with_user=False)
        frappe.set_user(user2)
        self.assertFalse(apis.my_service_detail(svc2.name)["capabilities"]["can_sso"])

    def test_get_panel_login_happy_path(self):
        cust_name, user_name = _make_customer()
        svc = self._sso_service(cust_name)
        frappe.set_user(user_name)
        with mock.patch.object(apis, "_adapter_for_plan", return_value=FakeSsoAdapter()):
            out = apis.get_panel_login(svc.name)
        self.assertTrue(out["url"].startswith("https://"))
        self.assertNotIn("api_secret", frappe.as_json(out).lower())
        comments = frappe.get_all("Comment", {"reference_doctype": "Service", "reference_name": svc.name}, ["content"])
        self.assertTrue(any("Panel login" in (c["content"] or "") for c in comments))

    def test_get_panel_login_gates(self):
        cust_name, user_name = _make_customer()
        svc = self._sso_service(cust_name, status="Suspended")
        frappe.set_user(user_name)
        with mock.patch.object(apis, "_adapter_for_plan", return_value=FakeSsoAdapter()):
            self.assertRaises(frappe.ValidationError, apis.get_panel_login, svc.name)
        frappe.set_user("Administrator")
        cust2, user2 = _make_customer()
        svc2 = self._sso_service(cust2)
        frappe.set_user(user2)
        with mock.patch.object(apis, "_adapter_for_plan", return_value=None):
            self.assertRaises(frappe.ValidationError, apis.get_panel_login, svc2.name)
        _other, other_user = _make_customer()
        frappe.set_user(other_user)
        with mock.patch.object(apis, "_adapter_for_plan", return_value=FakeSsoAdapter()):
            self.assertRaises(frappe.PermissionError, apis.get_panel_login, svc2.name)
