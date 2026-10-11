import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.tests.helpers import make_user
from lube_station.lube_station.customers import addresses


class TestAddresses(IntegrationTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def _customer(self, prefix: str):
        user = make_user(prefix)
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user, "status": "Active"}).insert()
        return cust.name, user

    def _add(self, **kw):
        base = {"address_title": "Home", "address_line1": "1 Main St", "city": "Springfield", "country": "India"}
        base.update(kw)
        return addresses.add_address(**base)["address"]

    def test_crud_and_defaults(self):
        cust_name, user = self._customer("addr")
        frappe.set_user(user)
        a = self._add()
        b = self._add(address_title="Office", address_type="Office", city="Mumbai")
        rows = addresses.my_addresses()
        self.assertEqual(len(rows), 2)
        # First address auto-defaulted both kinds.
        first = next(r for r in rows if r["name"] == a)
        self.assertEqual(first["is_primary_address"], 1)
        # Switch default.
        addresses.set_default_address(b, kind="billing")
        rows = addresses.my_addresses()
        self.assertEqual(next(r for r in rows if r["name"] == b)["is_primary_address"], 1)
        self.assertEqual(next(r for r in rows if r["name"] == a)["is_primary_address"], 0)
        # Edit + delete promotes survivor.
        addresses.update_address(a, city="Delhi")
        self.assertEqual(frappe.db.get_value("Address", a, "city"), "Delhi")
        addresses.delete_address(b)
        rows = addresses.my_addresses()
        self.assertEqual([r["name"] for r in rows], [a])
        self.assertEqual(rows[0]["is_primary_address"], 1)
        self.assertRaises(frappe.ValidationError, addresses.add_address,
                          address_title="X", address_line1="Y", city="Z", country="No Such Country")

    def test_isolation(self):
        cust_a, user_a = self._customer("addra")
        cust_b, user_b = self._customer("addrb")
        frappe.set_user(user_a)
        a = self._add()
        frappe.set_user(user_b)
        self.assertEqual(addresses.my_addresses(), [])
        self.assertRaises(frappe.DoesNotExistError, addresses.update_address, a, city="Hijack")
        self.assertRaises(frappe.DoesNotExistError, addresses.delete_address, a)
        self.assertRaises(frappe.DoesNotExistError, addresses.set_default_address, a)
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, addresses.my_addresses)
