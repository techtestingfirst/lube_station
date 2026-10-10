"""Live Nominet adapter tests. Socket is faked; no network happens."""

import struct

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.registrar.nominet import NominetAdapter, _frame


def frame(xml: str) -> bytes:
    return _frame(xml)


GREETING = """<?xml version="1.0"?><epp xmlns="urn:ietf:params:xml:ns:epp-1.0"><greeting><svID>test</svID></greeting></epp>"""


def result(code, inner=""):
    return (
        f'<?xml version="1.0"?><epp xmlns="urn:ietf:params:xml:ns:epp-1.0">'
        f"<response><result code='{code}'><msg>ok</msg></result>{inner}</response></epp>"
    )


def avail(name, flag):
    return result(1000, f"<resData><domain:chkData xmlns:domain='urn:ietf:params:xml:ns:domain-1.0'><domain:cd><domain:name avail='{flag}'>{name}</domain:name></domain:cd></domain:chkData></resData>")


class FakeSocket:
    def __init__(self, script):
        self.script = list(script)
        self.sent = []
        self._buf = b""
        self.closed = False

    def sendall(self, data):
        self.sent.append(data)
        length = struct.unpack(">I", data[:4])[0]
        assert len(data) == length, "frame length mismatch"
        body = data[4:].decode()
        reply = self.script.pop(0)(body) if callable(self.script[0]) else self.script.pop(0)
        self._buf += frame(reply)

    def recv(self, n):
        chunk, self._buf = self._buf[:n], self._buf[n:]
        return chunk

    def close(self):
        self.closed = True


def make_factory(sock, replies=None):
    sock._buf = frame(GREETING)
    sock.script = [result(1000)] + list(replies or []) + [result(1000)]
    return lambda: sock


class TestNominetLiveAdapter(IntegrationTestCase):
    def _account(self):
        from lube_station.lube_station.adapters.seed import seed

        seed()
        name = frappe.db.get_value("Registrar Account", {"registrar": "Nominet"}, "name")
        if name:
            return name, False
        doc = frappe.get_doc(
            {"doctype": "Registrar Account", "registrar": "Nominet", "active": 1}
        ).insert(ignore_permissions=True)
        doc.set("api_key", "REG-TAG")
        doc.set("api_secret", "pw123")
        doc.save(ignore_permissions=True)
        return doc.name, True

    def _drop(self, name, created):
        if created:
            try:
                frappe.delete_doc("Registrar Account", name, ignore_permissions=True, force=True)
            except Exception:
                pass

    def test_framing_and_login(self):
        sock = FakeSocket([])
        from lube_station.lube_station.adapters.registrar.nominet import EppSession

        session = EppSession("h", 700, "u", "p", make_factory(sock, sock.script)).open()
        self.assertTrue(any("<login>" in s.decode() for s in sock.sent))
        session.close()
        self.assertTrue(sock.closed)

    def test_check_and_register(self):
        name, created = self._account()
        try:
            sock = FakeSocket(
                [lambda b: avail("example.com", "1") if "<check>" in b else result(1000)]
            )
            out = NominetAdapter().check_availability("example.com", transport=make_factory(sock, sock.script))
            self.assertEqual(out["status"], "available")
            sent = b"".join(s[4:] for s in sock.sent).decode()
            self.assertIn("<domain:check", sent)

            contacts = {"registrant": "C1", "admin": "C1", "tech": "C1", "billing": "C1"}
            sock = FakeSocket([result(1000)])
            out = NominetAdapter().register_domain("n.uk", contacts, ["ns1.x"], transport=make_factory(sock, sock.script))
            self.assertEqual(out["registered"], "n.uk")
            sent = b"".join(s[4:] for s in sock.sent).decode()
            self.assertIn("<domain:create", sent)
            self.assertIn("<domain:hostObj>ns1.x</domain:hostObj>", sent)
        finally:
            self._drop(name, created)

    def test_transfer_renew_ns(self):
        name, created = self._account()
        try:
            sock = FakeSocket([result(1001)])
            out = NominetAdapter().transfer_domain("t.uk", "epp1", transport=make_factory(sock, sock.script))
            self.assertEqual(out["transferred"], "t.uk")

            info = result(
                1000,
                "<resData><domain:infData xmlns:domain='urn:ietf:params:xml:ns:domain-1.0'>"
                "<domain:exDate>2027-05-01T00:00:00.0Z</domain:exDate></domain:infData></resData>",
            )
            sock = FakeSocket([info, result(1000)])
            out = NominetAdapter().renew_domain("r.uk", 2, transport=make_factory(sock, sock.script))
            self.assertEqual(out["renewed"], "r.uk")
            sent = b"".join(s[4:] for s in sock.sent).decode()
            self.assertIn("<domain:curExpDate>2027-05-01</domain:curExpDate>", sent)

            sock = FakeSocket([result(1000)])
            out = NominetAdapter().update_nameservers("x.uk", ["ns1.x"], transport=make_factory(sock, sock.script))
            self.assertEqual(out["nameservers"], ["ns1.x"])
        finally:
            self._drop(name, created)
