"""Live OpenSRS adapter (XCP JSON over HTTPS, reseller credentials).

Sandbox by default: credentials come from the Registrar Account row
(api_key = reseller username, api_secret Password = private key). Test
endpoint is used unless the account row opts into production (manual gate:
only a human edits that row). HTTP is injectable so tests never touch the
network.

Signature formula per OpenSRS XCP spec: md5(md5(body + key) + key), sent as
X-Signature with X-Username. Attribute shapes follow the XCP domain/dns
objects; confirm against the live test endpoint once creds exist.
"""

import hashlib
import json
import time

import frappe

from lube_station.lube_station.adapters.utils import redact

from .base import RegistrarAdapter, normalize_availability

TEST_URL = "https://horizon.opensrs.net:55443"
LIVE_URL = "https://rr-n1-tor.opensrs.net:55443"
TIMEOUT = 20
RETRIES = 3


def _signature(body: str, key: str) -> str:
    inner = hashlib.md5((body + key).encode()).hexdigest()
    return hashlib.md5((inner + key).encode()).hexdigest()


def _http_post(url, headers, body, timeout):
    import requests

    return requests.post(url, headers=headers, data=body, timeout=timeout)


class OpenSrsAdapter(RegistrarAdapter):
    adapter_name = "OpenSRS"

    # -- connection -----------------------------------------------------
    def _account(self):
        name = frappe.db.get_value(
            "Registrar Account", {"registrar": "OpenSRS", "active": 1}, "name"
        )
        if not name:
            frappe.throw("No active OpenSRS Registrar Account")
        doc = frappe.get_doc("Registrar Account", name)
        username = doc.get_password(fieldname="api_key", raise_exception=False) or ""
        # api_key may be stored plain or as Password; fall back to raw value.
        if not username:
            username = (doc.get("api_key") or "").strip()
        key = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not username or not key:
            frappe.throw("OpenSRS account is missing API credentials")
        url = LIVE_URL if (doc.get("live_mode") or 0) else TEST_URL
        return username, key, url

    # -- transport ------------------------------------------------------
    def _call(self, action, obj, attributes=None, transport=None):
        username, key, url = self._account()
        transport = transport or _http_post
        payload = {
            "protocol": "XCP",
            "action": action,
            "object": obj,
            "attributes": attributes or {},
        }
        body = json.dumps(payload, separators=(",", ":"))
        headers = {
            "Content-Type": "application/json",
            "X-Username": username,
            "X-Signature": _signature(body, key),
        }
        safe_attrs = redact(payload["attributes"])
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(url, headers, body, TIMEOUT)
                return self._result(action, obj, safe_attrs, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"OpenSRS {obj}/{action} failed after {RETRIES} attempts: {last_error}")

    def _result(self, action, obj, safe_attrs, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else json.loads(resp)
        except Exception:
            frappe.throw(f"OpenSRS {obj}/{action} returned non-JSON response")
        code = out.get("response_code", 0)
        if code not in (200, 210):
            frappe.throw(
                f"OpenSRS {obj}/{action} rejected: {out.get('response_text', code)}",
                frappe.ValidationError,
            )
        return out.get("attributes") or {}

    # -- domain ops -----------------------------------------------------
    def check_availability(self, domain, transport=None):
        attrs = self._call("lookup", "domain", {"domain": domain}, transport)
        status = str(attrs.get("status", "")).lower()
        if status not in ("available", "taken", "premium"):
            status = "unknown"
        out = normalize_availability(domain, status)
        out["premium_price"] = attrs.get("premium_price", 0)
        return out

    def register_domain(self, domain, contacts, nameservers, transport=None):
        attrs = {
            "domain": domain,
            "period": 1,
            "contact_set": contacts or {},
            "custom_nameservers": 1 if nameservers else 0,
            "nameserver_list": [{"name": n} for n in (nameservers or [])],
        }
        self._call("sw_register", "domain", attrs, transport)
        return {"registered": domain}

    def transfer_domain(self, domain, auth_code, transport=None):
        self._call("sw_transfer", "domain", {"domain": domain, "auth_info": auth_code}, transport)
        return {"transferred": domain}

    def renew_domain(self, domain, years=1, transport=None):
        self._call("renew", "domain", {"domain": domain, "period": years or 1}, transport)
        return {"renewed": domain}

    def get_domain_info(self, domain, transport=None):
        attrs = self._call("get", "domain", {"domain": domain}, transport)
        return {"domain": domain, "info": attrs}

    def update_nameservers(self, domain, nameservers, transport=None):
        self._call(
            "modify",
            "domain",
            {
                "domain": domain,
                "custom_nameservers": 1,
                "nameserver_list": [{"name": n} for n in (nameservers or [])],
            },
            transport,
        )
        return {"domain": domain, "nameservers": nameservers}

    def update_contact(self, domain, contacts, transport=None):
        self._call("modify", "domain", {"domain": domain, "contact_set": contacts or {}}, transport)
        return {"domain": domain, "updated": True}

    def toggle_privacy(self, domain, enabled, transport=None):
        frappe.throw("OpenSRS privacy toggle is not mapped yet; enable it in the reseller console")

    # -- dns ops ----------------------------------------------------------
    def create_dns_record(self, domain, record, transport=None):
        self._call("add_record", "dns", {"domain": domain, "record": record}, transport)
        return {"created": True, "domain": domain}

    def update_dns_record(self, domain, record, transport=None):
        self._call("update_record", "dns", {"domain": domain, "record": record}, transport)
        return {"updated": True, "domain": domain}

    def delete_dns_record(self, domain, record_id, transport=None):
        self._call("delete_record", "dns", {"domain": domain, "record_id": record_id}, transport)
        return {"deleted": True, "domain": domain}
