class RegistrarAdapter:
    adapter_name = ""

    def check_availability(self, domain):
        raise NotImplementedError

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


def normalize_availability(domain: str, status: str) -> dict:
    return {"domain": domain, "status": status}
