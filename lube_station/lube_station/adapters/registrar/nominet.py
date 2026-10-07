"""Live Nominet adapter (EPP over TLS, login auth).

OTE sandbox by default (live host when the account row opts into live_mode).
EPP framing follows RFC 5730-5734 (4-byte length-prefixed XML over TLS 1.2+)
plus Nominet's domain commands: check/create/renew/transfer/info/update.
Each operation opens its own session (hello/login/command/logout): simple
and stateless. Contacts are referenced by explicit handle IDs; renew reads
its own expiry first. Privacy/DNS explicitly unmapped. Nothing connects
without account creds (manual gate).
"""

import socket
import ssl
import struct
import time
import xml.etree.ElementTree as ET

import frappe

from .base import RegistrarAdapter, normalize_availability

LIVE_HOST = ("epp.nominet.org.uk", 700)
TEST_HOST = ("epp.test.nominet.org.uk", 700)
TIMEOUT = 25
RETRIES = 2
NS = {
    "epp": "urn:ietf:params:xml:ns:epp-1.0",
    "domain": "urn:ietf:params:xml:ns:domain-1.0",
}

for _prefix, _uri in (("domain", NS["domain"]),):
    try:
        ET.register_namespace(_prefix, _uri)
    except Exception:
        pass

EPPTPL = '<?xml version="1.0" encoding="UTF-8"?><epp xmlns="urn:ietf:params:xml:ns:epp-1.0">{body}</epp>'


def _frame(payload: str) -> bytes:
    raw = payload.encode()
    return struct.pack(">I", len(raw) + 4) + raw


def _el(parent, tag, text=None, attrs=None):
    el = ET.SubElement(parent, tag, attrs or {})
    if text is not None:
        el.text = str(text)
    return el


class EppSession:
    """One TLS connection + login. Socket factory injectable for tests."""

    def __init__(self, host, port, login, password, factory=None):
        self.host = host
        self.port = port
        self.login = login
        self.password = password
        self.factory = factory or self._connect
        self.sock = None
        self._trid = 0

    def _connect(self):
        raw = socket.create_connection((self.host, self.port), TIMEOUT)
        ctx = ssl.create_default_context()
        return ctx.wrap_socket(raw, server_hostname=self.host)

    def open(self):
        self.sock = self.factory() if self.factory is not self._connect else self._connect()
        self._read()  # greeting
        cmd = ET.fromstring(f"<command><login><clID>{self.login}</clID><pw>{self.password}</pw><options><version>1.0</version><lang>en</lang></options><svcs><objURI>urn:ietf:params:xml:ns:domain-1.0</objURI><objURI>urn:ietf:params:xml:ns:host-1.0</objURI><objURI>urn:ietf:params:xml:ns:contact-1.0</objURI></svcs></login><clTRID>login-{id(self)}</clTRID></command>")
        code, _ = self.roundtrip(cmd)
        if code != 1000:
            frappe.throw(f"Nominet login rejected: {code}", frappe.ValidationError)
        return self

    def close(self):
        try:
            if self.sock:
                cmd = ET.fromstring("<command><logout/><clTRID>bye</clTRID></command>")
                self.roundtrip(cmd)
        except Exception:
            pass
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        self.sock = None

    def _read(self):
        header = b""
        while len(header) < 4:
            chunk = self.sock.recv(4 - len(header))
            if not chunk:
                raise ConnectionError("EPP connection closed")
            header += chunk
        (length,) = struct.unpack(">I", header)
        data = b""
        while len(data) < length - 4:
            chunk = self.sock.recv(length - 4 - len(data))
            if not chunk:
                raise ConnectionError("EPP connection closed")
            data += chunk
        return ET.fromstring(data.decode())

    def roundtrip(self, command_el):
        self._trid += 1
        trid = command_el.find("clTRID")
        if trid is None:
            trid = ET.SubElement(command_el, "clTRID")
            trid.text = f"lube-{self._trid}"
        self.sock.sendall(_frame(ET.tostring(command_el, encoding="unicode")))
        root = self._read()
        result = root.find("./{urn:ietf:params:xml:ns:epp-1.0}response/{urn:ietf:params:xml:ns:epp-1.0}result")
        code = int((result.attrib.get("code") if result is not None else "") or 0)
        return code, root

    def command(self, inner_xml: str):
        return self.roundtrip(ET.fromstring(f"<command>{inner_xml}<clTRID>x</clTRID></command>"))


class NominetAdapter(RegistrarAdapter):
    adapter_name = "Nominet"

    # -- connection -----------------------------------------------------
    def _account(self):
        name = frappe.db.get_value("Registrar Account", {"registrar": "Nominet", "active": 1}, "name")
        if not name:
            frappe.throw("No active Nominet Registrar Account")
        doc = frappe.get_doc("Registrar Account", name)
        login = doc.get_password(fieldname="api_key", raise_exception=False) or ""
        if not login:
            login = (doc.get("api_key") or "").strip()
        password = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not login or not password:
            frappe.throw("Nominet account is missing API credentials")
        host, port = LIVE_HOST if (doc.get("live_mode") or 0) else TEST_HOST
        return login, password, host, port

    def _session(self, factory=None):
        login, password, host, port = self._account()
        return EppSession(host, port, login, password, factory).open()

    def _run(self, fn, factory=None):
        session = self._session(factory)
        try:
            return fn(session)
        finally:
            session.close()

    # -- domain ops -----------------------------------------------------
    def check_availability(self, domain, transport=None):
        def op(session):
            code, root = session.command(
                f"<check><domain:check xmlns:domain='urn:ietf:params:xml:ns:domain-1.0'><domain:name>{domain}</domain:name></domain:check></check>"
            )
            el = root.find(".//{urn:ietf:params:xml:ns:domain-1.0}cd/{urn:ietf:params:xml:ns:domain-1.0}name")
            avail = (el.attrib.get("avail") if el is not None else "") == "1"
            return normalize_availability(domain, "available" if avail else "taken")

        return self._run(op, transport)

    def _handles(self, contacts):
        contacts = contacts or {}
        if contacts.get("registrant"):
            return {
                "registrant": contacts["registrant"],
                "admin": contacts.get("admin", contacts["registrant"]),
                "tech": contacts.get("tech", contacts["registrant"]),
                "billing": contacts.get("billing", contacts["registrant"]),
            }
        frappe.throw("Nominet needs explicit contact handles (registrant/admin/tech/billing)", frappe.ValidationError)

    def register_domain(self, domain, contacts, nameservers, transport=None):
        handles = self._handles(contacts)

        def op(session):
            ns = "".join(f"<domain:hostObj>{n}</domain:hostObj>" for n in (nameservers or []))
            code, root = session.command(
                "<create><domain:create xmlns:domain='urn:ietf:params:xml:ns:domain-1.0'>"
                f"<domain:name>{domain}</domain:name><domain:period unit='y'>1</domain:period>"
                f"<domain:ns>{ns}</domain:ns>"
                f"<domain:registrant>{handles['registrant']}</domain:registrant>"
                f"<domain:admin>{handles['admin']}</domain:admin>"
                f"<domain:tech>{handles['tech']}</domain:tech>"
                f"<domain:billing>{handles['billing']}</domain:billing>"
                "</domain:create></create>"
            )
            if code != 1000:
                frappe.throw(f"Nominet create rejected: {code}", frappe.ValidationError)
            return {"registered": domain}

        return self._run(op, transport)

    def transfer_domain(self, domain, auth_code, transport=None):
        def op(session):
            code, _ = session.command(
                "<transfer op='request'><domain:transfer xmlns:domain='urn:ietf:params:xml:ns:domain-1.0'>"
                f"<domain:name>{domain}</domain:name><domain:period unit='y'>1</domain:period>"
                f"<domain:authInfo><domain:pw>{auth_code}</domain:pw></domain:authInfo>"
                "</domain:transfer></transfer>"
            )
            if code not in (1000, 1001):
                frappe.throw(f"Nominet transfer rejected: {code}", frappe.ValidationError)
            return {"transferred": domain}

        return self._run(op, transport)

    def renew_domain(self, domain, years=1, transport=None):
        def op(session):
            code, root = session.command(
                f"<info><domain:info xmlns:domain='urn:ietf:params:xml:ns:domain-1.0'><domain:name>{domain}</domain:name></domain:info></info>"
            )
            ex = root.findtext(".//{urn:ietf:params:xml:ns:domain-1.0}exDate") or ""
            cur = ex[:10]
            if not cur:
                frappe.throw(f"Nominet has no expiry for {domain}", frappe.ValidationError)
            code, _ = session.command(
                "<renew><domain:renew xmlns:domain='urn:ietf:params:xml:ns:domain-1.0'>"
                f"<domain:name>{domain}</domain:name><domain:curExpDate>{cur}</domain:curExpDate>"
                f"<domain:period unit='y'>{years or 1}</domain:period>"
                "</domain:renew></renew>"
            )
            if code != 1000:
                frappe.throw(f"Nominet renew rejected: {code}", frappe.ValidationError)
            return {"renewed": domain}

        return self._run(op, transport)

    def get_domain_info(self, domain, transport=None):
        def op(session):
            code, root = session.command(
                f"<info><domain:info xmlns:domain='urn:ietf:params:xml:ns:domain-1.0'><domain:name>{domain}</domain:name></domain:info></info>"
            )
            if code != 1000:
                frappe.throw(f"Nominet info rejected: {code}", frappe.ValidationError)
            info = root.find(".//{urn:ietf:params:xml:ns:domain-1.0}infData")
            return {"domain": domain, "info": ET.tostring(info, encoding="unicode") if info is not None else {}}

        return self._run(op, transport)

    def update_nameservers(self, domain, nameservers, transport=None):
        def op(session):
            ns = "".join(f"<domain:hostObj>{n}</domain:hostObj>" for n in (nameservers or []))
            code, _ = session.command(
                "<update><domain:update xmlns:domain='urn:ietf:params:xml:ns:domain-1.0'>"
                f"<domain:name>{domain}</domain:name><domain:chg><domain:ns>{ns}</domain:ns></domain:chg>"
                "</domain:update></update>"
            )
            if code != 1000:
                frappe.throw(f"Nominet NS update rejected: {code}", frappe.ValidationError)
            return {"domain": domain, "nameservers": nameservers}

        return self._run(op, transport)

    def update_contact(self, domain, contacts, transport=None):
        handles = self._handles(contacts)

        def op(session):
            code, _ = session.command(
                "<update><domain:update xmlns:domain='urn:ietf:params:xml:ns:domain-1.0'>"
                f"<domain:name>{domain}</domain:name><domain:chg>"
                f"<domain:registrant>{handles['registrant']}</domain:registrant>"
                f"<domain:admin>{handles['admin']}</domain:admin>"
                f"<domain:tech>{handles['tech']}</domain:tech>"
                f"<domain:billing>{handles['billing']}</domain:billing>"
                "</domain:chg></domain:update></update>"
            )
            if code != 1000:
                frappe.throw(f"Nominet contact update rejected: {code}", frappe.ValidationError)
            return {"domain": domain, "updated": True}

        return self._run(op, transport)

    def toggle_privacy(self, domain, enabled, transport=None):
        frappe.throw("Nominet privacy is registry-managed (.uk individuals opt out automatically)")

    # -- dns ops ------------------------------------------------------------
    def create_dns_record(self, domain, record, transport=None):
        frappe.throw("Nominet does not host DNS records; use nameservers instead")

    def update_dns_record(self, domain, record, transport=None):
        frappe.throw("Nominet does not host DNS records; use nameservers instead")

    def delete_dns_record(self, domain, record_id, transport=None):
        frappe.throw("Nominet does not host DNS records; use nameservers instead")
