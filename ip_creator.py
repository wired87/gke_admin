from google.cloud import dns
import subprocess

from utils.run_subprocess import exec_cmd


class IPManager:
    def __init__(
            self,
            project_id: str,
            region: str,
            domain: str,
            dns_zone: str
    ):
        """
        :param project_id: GCP Project ID
        :param region: Region where GKE is running (e.g., 'us-central1')
        :param domain: Domain name managed in Cloud DNS (e.g., 'clusterexpress.com.')
        :param dns_zone: Cloud DNS zone name (not domain, but the zone identifier)
        """
        self.project_id = project_id
        self.region = region
        self.domain = domain.rstrip(".") + "."  # enforce trailing dot
        self.dns_zone = dns_zone
        self.dns_client = dns.Client(project=project_id)

    def reserve_static_ip(self, name: str) -> str:
        """
        Reserve a static external IP address in the given region.
        :param name: Name for the reserved IP (e.g., 'my-ingress-ip')
        :return: IP address as string
        """
        cmd = [
            "gcloud", "compute", "addresses", "create", name,
            "--region", self.region,
            "--project", self.project_id
        ]
        subprocess.run(cmd, check=True)

        # Fetch the reserved IP
        cmd = [
            "gcloud", "compute", "addresses", "describe", name,
            "--region", self.region,
            "--project", self.project_id,
            "--format=value(address)"
        ]
        ip = subprocess.check_output(cmd).decode("utf-8").strip()
        return ip


    def save_existing_ip(
            self,
            ip,
            ip_name,
    ):
        print(f"Save IP {ip} under name {ip_name}")
        cmd = [
            "gcloud", "compute", "addresses", "create", ip_name,
            "--addresses", ip,
            "--region", self.region,
            "--project", self.project_id
        ]
        exec_cmd(cmd)
        print(f"✅ IP {ip} wurde als statische Adresse {ip_name} reserviert.")
        return ip

    def get_ip_by_name(self, name: str) -> str or None:
        """
        Holt eine reservierte IP anhand ihres Namens.
        """
        cmd = [
            "gcloud", "compute", "addresses", "describe", name,
            "--region", self.region,
            "--project", self.project_id,
            "--format=value(address)"
        ]
        try:
            ip = subprocess.check_output(cmd).decode("utf-8").strip()
            return ip if ip else None
        except subprocess.CalledProcessError:
            return None

    def delete_ip(self, name: str):
        """
        Löscht eine reservierte IP anhand ihres Namens.
        """
        existing_ip: str or None = self.get_ip_by_name(name)
        if existing_ip is None:
            print(f"No Ip specified under {name}")
            return

        print(f"Deleting IP {name}")

        cmd = [
            "gcloud", "compute", "addresses", "delete", name,
            "--region", self.region,
            "--project", self.project_id,
            "-q"  # skip confirmation
        ]
        exec_cmd(cmd)
        print(f"🗑️ Statische IP {name} gelöscht.")


    def create_dns_record(self, record_name: str, ip_address: str, ttl: int = 300):
        """
        Create/replace an A record in Cloud DNS pointing to the reserved IP.
        :param record_name: Subdomain (e.g., 'sims' for sims.clusterexpress.com)
        :param ip_address: Static IP to point to
        :param ttl: Time-to-live (seconds)
        """
        zone = self.dns_client.zone(self.dns_zone)
        fqdn = f"{record_name}.{self.domain}"

        # Remove old record if exists
        changes = zone.changes()
        records = list(zone.list_resource_record_sets())
        for r in records:
            if r.name == fqdn and r.record_type == "A":
                changes.delete_record_set(r)

        # Add new record
        record_set = zone.resource_record_set(fqdn, "A", ttl, [ip_address])
        changes.add_record_set(record_set)
        changes.create()
        print(f"✅ DNS record created: {fqdn} → {ip_address}")


# Example usage:
if __name__ == "__main__":
    manager = IPManager(
        project_id="aixr-401704",
        region="us-central1",
        domain="clusterexpress.com",
        dns_zone="clusterexpress-zone"  # The DNS zone you created in Cloud DNS
    )

    ip = manager.reserve_static_ip("my-ingress-ip")
    print("Reserved IP:", ip)

    manager.create_dns_record("sims", ip)
