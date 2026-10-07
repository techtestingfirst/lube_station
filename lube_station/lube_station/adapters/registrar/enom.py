"""Live eNom adapter (reseller interface.asp API, login auth).

Test host by default (live host when the account row opts into live_mode).
Call structure per eNom docs: command/sld/tld/uid/pw/responsetype=xml;
responses carry RRPCode/RRPText. IP allowlisting + reseller credentials are
the seller's job. Shapes for purchase/contacts/NS follow the classic eNom
field names — confirm once against the test host with real creds.
"""

import time
import urllib.parse
import xml.etree.ElementTree as ET

import frappe

from .base import RegistrarAdapter, normalize_availability

LIVE_URL = "https://reseller.enom.com/interface.asp"
TEST_URL = "https://resellertest.enom.com/interface.asp"
TIMEOUT = 20
RETRIES = 3


def _http_post(url, headers, body, timeout):
    import requests

    return requests.post(url, headers=headers, data=body, timeout=timeout)


def split_domain(domain: str) -> tuple:
    parts = domain.strip().lower().split(".")
    if len(parts) < 2:
        frappe.throw(f"Invalid domain {domain}")
    return ".".join(parts[:-1]), parts[-1]


class EnomAdapter(RegistrarAdapter):
    adapter_name = "eNom"

    # -- connection -----------------------------------------------------
    def _account(self):
        name = frappe.db.get_value("Registrar Account", {"registrar": "eNom", "active": 1}, "name")
        if not name:
            frappe.throw("No active eNom Registrar Account")
        doc = frappe.get_doc("Registrar Account", name)
        uid = doc.get_password(fieldname="api_key", raise_exception=False) or ""
        if not uid:
            uid = (doc.get("api_key") or "").strip()
        pw = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not uid or not pw:
            frappe.throw("eNom account is missing API credentials")
        url = LIVE_URL if (doc.get("live_mode") or 0) else TEST_URL
        return uid, pw, url

    # -- transport ------------------------------------------------------
    def _call(self, command, params, transport=None):
        uid, pw, url = self._account()
        transport = transport or _http_post
        query = {"command": command, "uid": uid, "pw": pw, "responsetype": "xml"}
        query.update(params or {})
        body = urllib.parse.urlencode(query)
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(url, {"Content-Type": "application/x-www-form-urlencoded"}, body, TIMEOUT)
                return self._result(command, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                self._audit(command, "Retry", str(e)[:500])
                time.sleep(min(2**attempt, 8))
        self._audit(command, "Failed", str(last_error)[:500])
        frappe.throw(f"eNom {command} failed after {RETRIES} attempts: {last_error}")

    def _audit(self, command, status, error_text):
        try:
            provider = frappe.db.get_value("Infrastructure Provider", {"status": "Active"}, "name")
            if not provider or not frappe.db.exists("DocType", "Provider API Log"):
                return
            frappe.get_doc(
                {
                    "doctype": "Provider API Log",
                    "provider": provider,
                    "action": f"enom:{command}",
                    "status": status,
                    "error_text": error_text,
                }
            ).insert(ignore_permissions=True)
        except Exception:
            pass

    def _result(self, command, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            root = ET.fromstring(resp.text if hasattr(resp, "text") else resp)
        except Exception:
            frappe.throw(f"eNom {command} returned non-XML response")
        code = (root.findtext("RRPCode") or "").strip()
        text = (root.findtext("RRPText") or "").strip()
        if not code.startswith("2"):
            self._audit(command, "Failed", text[:500])
            frappe.throw(f"eNom {command} rejected ({code}): {text}", frappe.ValidationError)
        return root

    # -- domain ops -----------------------------------------------------
    def check_availability(self, domain, transport=None):
        sld, tld = split_domain(domain)
        root = self._call("check", {"sld": sld, "tld": tld}, transport)
        code = (root.findtext("RRPCode") or "").strip()
        status = "available" if code == "210" else "taken"
        out = normalize_availability(domain, status)
        return out

    def register_domain(self, domain, contacts, nameservers, transport=None):
        sld, tld = split_domain(domain)
        params = {"sld": sld, "tld": tld, "NumYears": 1, "UseDNS": "default"}
        params.update(self._contact_params(contacts or {}))
        for i, ns in enumerate(list(nameservers or [])[:12], 1):
            params[f"NS{i}"] = ns
        self._call("purchase", params, transport)
        return {"registered": domain}

    def transfer_domain(self, domain, auth_code, transport=None):
        sld, tld = split_domain(domain)
        self._call("Transfer", {"sld": sld, "tld": tld, "AuthInfo": auth_code}, transport)
        return {"transferred": domain}

    def renew_domain(self, domain, years=1, transport=None):
        self._call("Extend", {"Domain": domain, "NumYears": years or 1}, transport)
        return {"renewed": domain}

    def get_domain_info(self, domain, transport=None):
        root = self._call("GetInfo", {"Domain": domain}, transport)
        return {"domain": domain, "info": ET.tostring(root, encoding="unicode")}

    def update_nameservers(self, domain, nameservers, transport=None):
        params = {"Domain": domain}
        for i, ns in enumerate(list(nameservers or [])[:12], 1):
            params[f"NS{i}"] = ns
        self._call("ModifyNS", params, transport)
        return {"domain": domain, "nameservers": nameservers}

    def update_contact(self, domain, contacts, transport=None):
        params = {"Domain": domain}
        params.update(self._contact_params(contacts or {}))
        self._call("UpdateContacts", params, transport)
        return {"domain": domain, "updated": True}

    def toggle_privacy(self, domain, enabled, transport=None):
        frappe.throw("eNom ID Protect is not mapped yet; enable it in the reseller panel")

    # -- dns ops ------------------------------------------------------------
    def create_dns_record(self, domain, record, transport=None):
        frappe.throw("eNom DNS hosting is not mapped yet; point nameservers at a DNS host")

    def update_dns_record(self, domain, record, transport=None):
        frappe.throw("eNom DNS hosting is not mapped yet; point nameservers at a DNS host")

    def delete_dns_record(self, domain, record_id, transport=None):
        frappe.throw("eNom DNS hosting is not mapped yet; point nameservers at a DNS host")

    # -- helpers ----------------------------------------------------------
    def _contact_params(self, contacts):
        kinds = {"owner": "Registrant", "admin": "Admin", "tech": "Tech", "billing": "AuxBilling"}
        fields = ("FirstName", "LastName", "OrganizationName", "Address1", "City",
                  "StateProvince", "PostalCode", "Country", "EmailAddress", "Phone")
        out = {}
        for key, prefix in kinds.items():
            src = contacts.get(key) or {}
            if not isinstance(src, dict):
                continue
            for field in fields:
                if src.get(field):
                    out[f"{prefix}{field}"] = src[field]
        return out
