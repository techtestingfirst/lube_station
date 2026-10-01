from .base import RegistrarAdapter, normalize_availability


class _Mvp(RegistrarAdapter):
    def check_availability(self, domain):
        return normalize_availability(domain, "available")

    def register_domain(self, domain, contacts, nameservers):
        return {"registered": domain}

    def transfer_domain(self, domain, auth_code):
        return {"transferred": domain}

    def renew_domain(self, domain, years=1):
        return {"renewed": domain, "years": years}

    def get_domain_info(self, domain):
        return {"domain": domain}

    def update_nameservers(self, domain, nameservers):
        return {"domain": domain, "nameservers": nameservers}

    def create_dns_record(self, domain, record):
        return {"created": record}

    def update_dns_record(self, domain, record):
        return {"updated": record}

    def delete_dns_record(self, domain, record_id):
        return {"deleted": record_id}

    def update_contact(self, domain, contacts):
        return {"updated": domain}

    def toggle_privacy(self, domain, enabled):
        return {"domain": domain, "privacy": enabled}


class OpenSrsAdapter(_Mvp):
    adapter_name = "OpenSRS"


class NamecheapAdapter(_Mvp):
    adapter_name = "Namecheap"


class GodaddyAdapter(_Mvp):
    adapter_name = "GoDaddy"


class LogicBoxesAdapter(_Mvp):
    adapter_name = "ResellerClub / LogicBoxes"
