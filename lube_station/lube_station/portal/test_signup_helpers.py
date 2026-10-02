from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.portal import apis


class TestSignupHelpers(IntegrationTestCase):
    def test_country_list(self):
        countries = apis.country_list()
        self.assertGreater(len(countries), 200)
        india = [c for c in countries if c["name"] == "India"]
        self.assertTrue(india and india[0]["code"] == "IN")

    def test_pincode_invalid(self):
        self.assertRaises(frappe.ValidationError, apis.pincode_lookup, "!!")

    def test_pincode_india(self):
        fake = [{"Status": "Success", "PostOffice": [{"Name": "Connaught Place", "District": "New Delhi", "State": "Delhi"}]}]
        with patch("frappe.integrations.utils.make_get_request", return_value=fake):
            out = apis.pincode_lookup("110001", "India")
        self.assertEqual(out["city"], "New Delhi")
        self.assertEqual(out["state"], "Delhi")

    def test_pincode_india_not_found(self):
        with patch("frappe.integrations.utils.make_get_request", return_value=[{"Status": "Error", "PostOffice": []}]):
            self.assertRaises(frappe.ValidationError, apis.pincode_lookup, "000000", "India")

    def test_pincode_foreign(self):
        fake = {"places": [{"place name": "Beverly Hills", "state": "California"}]}
        with patch("frappe.integrations.utils.make_get_request", return_value=fake):
            out = apis.pincode_lookup("90210", "United States")
        self.assertEqual(out["city"], "Beverly Hills")
        self.assertEqual(out["state"], "California")

    def test_pincode_api_down_friendly(self):
        with patch("frappe.integrations.utils.make_get_request", side_effect=Exception("down")):
            self.assertRaises(frappe.ValidationError, apis.pincode_lookup, "110001", "India")
