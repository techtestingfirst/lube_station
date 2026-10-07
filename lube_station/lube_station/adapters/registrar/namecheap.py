"""Live Namecheap adapter (XML API over HTTPS, key + whitelisted IP).

Sandbox by default (api.sandbox.namecheap.com). Credentials come from the
Registrar Account row (api_key = ApiUser, api_secret Password = ApiKey,
client_ip = egress IP or blank for auto-detect). Command shapes follow the
official Namecheap API docs. Note setHosts replaces the WHOLE record set, so
update/delete read first. Nothing is contacted without account creds.
"""

import time
import urllib.parse
import xml.etree.ElementTree as ET

import frappe

from lube_station.lube_station.adapters.utils import redact

from .base import RegistrarAdapter, normalize_availability

LIVE_URL = "https://api.namecheap.com/xml.response"
TEST_URL = "https://api.sandbox.namecheap.com/xml.response"
TIMEOUT = 20
RETRIES = 3


def _http_post(url, headers, body, timeout):
    import requests

    return requests.post(url, headers=headers, data=body, timeout=timeout)


class NamecheapAdapter(RegistrarAdapter):
    adapter_name = "Namecheap"

    # -- connection -----------------------------------------------------
    def _account(self):
        name = frappe.db.get_value(
            "Registrar Account", {"registrar": "Namecheap", "active": 1}, "name"
        )
        if not name:
            frappe.throw("No active Namecheap Registrar Account")
        doc = frappe.get_doc("Registrar Account", name)
        username = doc.get_password(fieldname="api_key", raise_exception=False) or ""
        if not username:
            username = (doc.get("api_key") or "").strip()
        key = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not username or not key:
            frappe.throw("Namecheap account is missing API credentials")
        client_ip = (doc.get("client_ip") or "").strip() or self._detect_ip()
        url = LIVE_URL if (doc.get("live_mode") or 0) else TEST_URL
        return username, key, client_ip, url

    def _detect_ip(self):
        try:
            import requests

            return requests.get("https://api.ipify.org", timeout=5).text.strip()
        except Exception:
            frappe.throw("Set Client IP on the Namecheap Registrar Account")

    # -- transport ------------------------------------------------------
    def _call(self, command, params, transport=None):
        username, key, client_ip, url = self._account()
        transport = transport or _http_post
        query = {
            "ApiUser": username,
            "ApiKey": key,
            "UserName": username,
            "ClientIp": client_ip,
            "Command": command,
        }
        query.update(params or {})
        safe = redact(query)
        body = urllib.parse.urlencode(query)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(url, headers, body, TIMEOUT)
                return self._result(command, safe, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"Namecheap {command} failed after {RETRIES} attempts: {last_error}")

    def _result(self, command, safe, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            root = ET.fromstring(resp.text if hasattr(resp, "text") else resp)
        except Exception:
            frappe.throw(f"Namecheap {command} returned non-XML response")
        if root.attrib.get("Status", "").upper() != "OK":
            errs = [e.text for e in root.findall(".//Errors/Error") if e.text]
            frappe.throw(f"Namecheap {command} rejected: {'; '.join(errs) or 'unknown'}", frappe.ValidationError)
        return root

    # -- domain ops -----------------------------------------------------
    def check_availability(self, domain, transport=None):
        root = self._call("namecheap.domains.check", {"DomainList": domain}, transport)
        el = root.find(".//DomainCheckResult")
        if el is None:
            return normalize_availability(domain, "unknown")
        available = (el.attrib.get("Available", "false")).lower() == "true"
        premium = float(el.attrib.get("PremiumRegistrationPrice") or 0) > 0
        status = "available" if available else "taken"
        if available and premium:
            status = "premium"
        out = normalize_availability(domain, status)
        out["premium_price"] = float(el.attrib.get("PremiumRegistrationPrice") or 0)
        return out

    def register_domain(self, domain, contacts, nameservers, transport=None):
        params = {"DomainName": domain, "Years": 1, "AddFreeWhoisguard": "yes"}
        params.update(self._contact_params(contacts or {}))
        if nameservers:
            params["Nameservers"] = ",".join(nameservers)
        self._call("namecheap.domains.create", params, transport)
        return {"registered": domain}

    def transfer_domain(self, domain, auth_code, transport=None):
        self._call(
            "namecheap.domains.transfer.create",
            {"DomainName": domain, "Years": 1, "EPPCode": auth_code},
            transport,
        )
        return {"transferred": domain}

    def renew_domain(self, domain, years=1, transport=None):
        self._call(
            "namecheap.domains.renew", {"DomainName": domain, "Years": years or 1}, transport
        )
        return {"renewed": domain}

    def get_domain_info(self, domain, transport=None):
        root = self._call("namecheap.domains.getInfo", {"DomainName": domain}, transport)
        info = root.find(".//DomainGetInfoResult")
        return {"domain": domain, "info": ET.tostring(info, encoding="unicode") if info is not None else {}}

    def update_nameservers(self, domain, nameservers, transport=None):
        self._call(
            "namecheap.domains.dns.setCustom",
            {"DomainName": domain, "NameServers": ",".join(nameservers or [])},
            transport,
        )
        return {"domain": domain, "nameservers": nameservers}

    def update_contact(self, domain, contacts, transport=None):
        params = {"DomainName": domain}
        params.update(self._contact_params(contacts or {}))
        self._call("namecheap.domains.setContacts", params, transport)
        return {"domain": domain, "updated": True}

    def toggle_privacy(self, domain, enabled, transport=None):
        if not enabled:
            frappe.throw("Namecheap WhoisGuard disable is not mapped yet; use the Namecheap panel")
        self._call("namecheap.whoisguard.allot", {"DomainName": domain, "Years": 1}, transport)
        return {"domain": domain, "privacy": True}

    # -- dns ops (setHosts replaces all: read-modify-write) ---------------
    def _hosts(self, domain, transport):
        root = self._call("namecheap.domains.dns.getHosts", {"DomainName": domain}, transport)
        hosts = []
        for h in root.findall(".//host"):
            hosts.append({k: (h.attrib.get(k) or "") for k in ("HostId", "Name", "Type", "Address", "MXPref", "TTL")})
        return hosts

    def create_dns_record(self, domain, record, transport=None):
        hosts = self._hosts(domain, transport)
        hosts.append(self._to_host(record))
        self._push_hosts(domain, hosts, transport)
        return {"created": True, "domain": domain}

    def update_dns_record(self, domain, record, transport=None):
        record = dict(record or {})
        hosts = self._hosts(domain, transport)
        needle = str(record.get("HostId") or record.get("host") or record.get("hostname") or "")
        hosts = [h for h in hosts if h.get("HostId") != needle and h.get("Name") != needle]
        hosts.append(self._to_host(record))
        self._push_hosts(domain, hosts, transport)
        return {"updated": True, "domain": domain}

    def delete_dns_record(self, domain, record_id, transport=None):
        hosts = self._hosts(domain, transport)
        hosts = [h for h in hosts if h.get("HostId") != str(record_id)]
        self._push_hosts(domain, hosts, transport)
        return {"deleted": True, "domain": domain}

    def _push_hosts(self, domain, hosts, transport):
        params = {"DomainName": domain}
        for i, h in enumerate(hosts, 1):
            params[f"HostName{i}"] = h.get("Name", "@")
            params[f"RecordType{i}"] = h.get("Type", "A")
            params[f"Address{i}"] = h.get("Address", "")
            params[f"MXPref{i}"] = h.get("MXPref", "10")
            params[f"TTL{i}"] = h.get("TTL", "1800")
        self._call("namecheap.domains.dns.setHosts", params, transport)

    # -- helpers ----------------------------------------------------------
    def _to_host(self, record):
        record = record or {}
        return {
            "HostId": str(record.get("HostId") or ""),
            "Name": str(record.get("host") or record.get("hostname") or record.get("Name") or "@"),
            "Type": str(record.get("type") or record.get("RecordType") or "A"),
            "Address": str(record.get("value") or record.get("Address") or ""),
            "MXPref": str(record.get("MXPref") or "10"),
            "TTL": str(record.get("ttl") or record.get("TTL") or "1800"),
        }

    def _contact_params(self, contacts):
        """Map {owner/admin/tech/billing: {FirstName...}} to Namecheap fields."""
        kinds = {"owner": "Registrant", "admin": "Admin", "tech": "Tech", "billing": "AuxBilling"}
        fields = ("FirstName", "LastName", "OrganizationName", "JobTitle", "Address1", "Address2",
                  "City", "StateProvince", "PostalCode", "Country", "Phone", "EmailAddress")
        out = {}
        for key, prefix in kinds.items():
            for field in fields:
                val = (contacts.get(key) or {}).get(field) if isinstance(contacts.get(key), dict) else None
                if val:
                    out[f"{prefix}{field}"] = val
        return out
