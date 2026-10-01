from .base import RegistrarAdapter


class _Stub(RegistrarAdapter):
    def check_availability(self, domain):
        raise NotImplementedError("Phase 2/3 registrar inactive")

    def register_domain(self, domain, contacts, nameservers):
        raise NotImplementedError

    def transfer_domain(self, domain, auth_code):
        raise NotImplementedError

    def renew_domain(self, domain, years=1):
        raise NotImplementedError

    def get_domain_info(self, domain):
        raise NotImplementedError

    def update_nameservers(self, domain, nameservers):
        raise NotImplementedError

    def create_dns_record(self, domain, record):
        raise NotImplementedError

    def update_dns_record(self, domain, record):
        raise NotImplementedError

    def delete_dns_record(self, domain, record_id):
        raise NotImplementedError

    def update_contact(self, domain, contacts):
        raise NotImplementedError

    def toggle_privacy(self, domain, enabled):
        raise NotImplementedError


class EnomAdapter(_Stub):
    adapter_name = "eNom"


class CentralNicAdapter(_Stub):
    adapter_name = "CentralNic Reseller"


class HexonetAdapter(_Stub):
    adapter_name = "HEXONET"


class PorkbunAdapter(_Stub):
    adapter_name = "Porkbun"


class InternetBsAdapter(_Stub):
    adapter_name = "Internet.bs"


class NominetAdapter(_Stub):
    adapter_name = "Nominet"
