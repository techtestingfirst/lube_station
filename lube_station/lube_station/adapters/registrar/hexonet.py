"""Live HEXONET adapter (ISPAPI command blocks over HTTPS, login auth).

OTE sandbox by default (live host when the account row opts into live_mode).
Shapes follow the official HEXONET API docs: CheckDomain (210/211),
AddContact, AddDomain with contact handles, TransferDomain, RenewDomain with
expiry year from StatusDomain, ModifyDomain NS/contacts, StatusDomain info.
Privacy/DNS record ops explicitly unmapped. Nothing fires without creds.
"""

import time

import frappe

from .base import RegistrarAdapter, normalize_availability

LIVE_URL = "https://api.ispapi.net/api/call.cgi"
TEST_URL = "https://api-ote.ispapi.net/api/call.cgi"
TIMEOUT = 20
RETRIES = 3


def _http_post(url, headers, body, timeout):
    import requests

    return requests.post(url, headers=headers, data=body.encode(), timeout=timeout)


def encode_command(command: str, params: dict) -> str:
    lines = ["[COMMAND]", f"COMMAND = {command}"]
    for key, val in (params or {}).items():
        if isinstance(val, (list, tuple)):
            for item in val:
                lines.append(f"{key} = {item}")
        elif val is not None:
            lines.append(f"{key} = {val}")
    lines.append("EOF")
    return "\r\n".join(lines) + "\r\n"


def parse_response(text: str) -> dict:
    section, out = None, {"property": {}}
    for raw in (text or "").splitlines():
        line = raw.strip()
        if line == "[RESPONSE]":
            section = "response"
            continue
        if line == "EOF" or not line or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if key == "CODE":
            out["code"] = val
        elif key == "DESCRIPTION":
            out["description"] = val
        elif key.startswith("PROPERTY["):
            inner = key[len("PROPERTY["):]
            name, _, rest = inner.partition("]")
            idx = rest.strip("[] ")
            bucket = out["property"].setdefault(name, [])
            while len(bucket) <= (int(idx) if idx.isdigit() else 0):
                bucket.append("")
            bucket[int(idx) if idx.isdigit() else 0] = val
    return out


class HexonetAdapter(RegistrarAdapter):
    adapter_name = "HEXONET"

    # -- connection -----------------------------------------------------
    def _account(self):
        name = frappe.db.get_value("Registrar Account", {"registrar": "HEXONET", "active": 1}, "name")
        if not name:
            frappe.throw("No active HEXONET Registrar Account")
        doc = frappe.get_doc("Registrar Account", name)
        login = doc.get_password(fieldname="api_key", raise_exception=False) or ""
        if not login:
            login = (doc.get("api_key") or "").strip()
        password = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not login or not password:
            frappe.throw("HEXONET account is missing API credentials")
        url = LIVE_URL if (doc.get("live_mode") or 0) else TEST_URL
        return login, password, url

    # -- transport ------------------------------------------------------
    def _call(self, command, params, transport=None):
        login, password, url = self._account()
        transport = transport or _http_post
        merged = {"s_login": login, "s_pw": password}
        merged.update(params or {})
        body = encode_command(command, merged)
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(url, {"Content-Type": "text/plain"}, body, TIMEOUT)
                return self._result(command, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"HEXONET {command} failed after {RETRIES} attempts: {last_error}")

    def _result(self, command, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = parse_response(resp.text if hasattr(resp, "text") else resp)
        except Exception:
            frappe.throw(f"HEXONET {command} returned unparseable response")
        if not str(out.get("code", "")).startswith("2"):
            frappe.throw(
                f"HEXONET {command} rejected ({out.get('code')}): {out.get('description')}",
                frappe.ValidationError,
            )
        return out

    def _prop(self, out, name, default=""):
        vals = (out.get("property") or {}).get(name) or []
        return vals[0] if vals else default

    # -- domain ops -----------------------------------------------------
    def check_availability(self, domain, transport=None):
        out = self._call("CheckDomain", {"DOMAIN": domain}, transport)
        code = str(out.get("code", ""))
        status = "available" if code == "210" else ("taken" if code == "211" else "unknown")
        return normalize_availability(domain, status)

    def _contact_handle(self, detail, transport):
        if isinstance(detail, str) and detail:
            return detail
        detail = detail or {}
        prop = self._call(
            "AddContact",
            {
                "FIRSTNAME": detail.get("FirstName", "-"),
                "LASTNAME": detail.get("LastName", "-"),
                "ORGANIZATION": detail.get("OrganizationName", ""),
                "STREET": detail.get("Address1", "-"),
                "CITY": detail.get("City", "-"),
                "STATE": detail.get("StateProvince", "-"),
                "ZIP": detail.get("PostalCode", "-"),
                "COUNTRY": detail.get("Country", "DE"),
                "PHONE": detail.get("Phone", "+49.000000"),
                "EMAIL": detail.get("EmailAddress", "admin@example.invalid"),
            },
            transport,
        )
        handle = self._prop(prop, "CONTACT")
        if not handle:
            frappe.throw("HEXONET contact create returned no handle", frappe.ValidationError)
        return handle

    def _handles(self, contacts, transport):
        contacts = contacts or {}
        if contacts.get("ownercontact0"):
            return {
                "OWNERCONTACT0": contacts["ownercontact0"],
                "ADMINCONTACT0": (contacts.get("admincontact") or [""])[0],
                "TECHCONTACT0": (contacts.get("techcontact") or [""])[0],
                "BILLINGCONTACT0": (contacts.get("billingcontact") or [""])[0],
            }
        owner = self._contact_handle(contacts.get("owner"), transport)
        other = self._contact_handle(contacts.get("admin") or contacts.get("owner"), transport)
        return {
            "OWNERCONTACT0": owner,
            "ADMINCONTACT0": other,
            "TECHCONTACT0": other,
            "BILLINGCONTACT0": other,
        }

    def register_domain(self, domain, contacts, nameservers, transport=None):
        params = {"DOMAIN": domain, "PERIOD": "1Y", **self._handles(contacts, transport)}
        for i, ns in enumerate(list(nameservers or [])):
            params[f"NAMESERVER{i}"] = ns
        self._call("AddDomain", params, transport)
        return {"registered": domain}

    def transfer_domain(self, domain, auth_code, transport=None):
        self._call("TransferDomain", {"DOMAIN": domain, "AUTH": auth_code, "ACTION": "REQUEST"}, transport)
        return {"transferred": domain}

    def renew_domain(self, domain, years=1, transport=None):
        info = self.get_domain_info(domain, transport)
        year = self._expiry_year(info.get("raw") or {})
        self._call("RenewDomain", {"DOMAIN": domain, "PERIOD": f"{years or 1}Y", "EXPIRATION": year}, transport)
        return {"renewed": domain}

    def _expiry_year(self, info):
        import datetime
        import re

        candidates = []
        def walk(node):
            if isinstance(node, dict):
                for key, val in node.items():
                    if "expir" in str(key).lower():
                        candidates.append(val)
                    walk(val)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(info)
        for val in candidates:
            if isinstance(val, list):
                val = val[0] if val else ""
            match = re.search(r"(19|20)\d{2}", str(val))
            if match:
                return int(match.group(0))
        return datetime.datetime.now().year

    def get_domain_info(self, domain, transport=None):
        out = self._call("StatusDomain", {"DOMAIN": domain}, transport)
        return {"domain": domain, "info": out.get("property"), "raw": out.get("property")}

    def update_nameservers(self, domain, nameservers, transport=None):
        params = {"DOMAIN": domain}
        for i, ns in enumerate(list(nameservers or [])):
            params[f"NAMESERVER{i}"] = ns
        self._call("ModifyDomain", params, transport)
        return {"domain": domain, "nameservers": nameservers}

    def update_contact(self, domain, contacts, transport=None):
        contacts = contacts or {}
        params = {"DOMAIN": domain}
        mapping = {"owner": "OWNERCONTACT", "admin": "ADMINCONTACT", "tech": "TECHCONTACT", "billing": "BILLINGCONTACT"}
        for key, prefix in mapping.items():
            handle = contacts.get(key if key != "owner" else "ownercontact0") or contacts.get(key)
            if isinstance(handle, list):
                handle = handle[0] if handle else ""
            if isinstance(handle, dict):
                handle = self._contact_handle(handle, transport)
            if handle:
                params[f"{prefix}0"] = handle
        if len(params) == 1:
            frappe.throw("No contact handles to update", frappe.ValidationError)
        self._call("ModifyDomain", params, transport)
        return {"domain": domain, "updated": True}

    def toggle_privacy(self, domain, enabled, transport=None):
        frappe.throw("HEXONET privacy toggle is not mapped yet")

    # -- dns ops ------------------------------------------------------------
    def create_dns_record(self, domain, record, transport=None):
        frappe.throw("HEXONET DNS records are not mapped yet; use nameservers instead")

    def update_dns_record(self, domain, record, transport=None):
        frappe.throw("HEXONET DNS records are not mapped yet; use nameservers instead")

    def delete_dns_record(self, domain, record_id, transport=None):
        frappe.throw("HEXONET DNS records are not mapped yet; use nameservers instead")
