from google.cloud import dns
import subprocess
from utils.run_subprocess import exec_cmd

class DNSManager:

    """
    # todo enable CoreDNS stub domain or external-dns so the internal DNS resolution also points myapp.example.com → LoadBalancer IP. That way internal and external clients resolve the same host

    """


    def __init__(
            self,
            project_id: str,
            region: str,
            dns_name: str,
    ):
        """
        :param project_id: GCP Project ID
        :param region: Region where GKE is running (e.g., 'us-central1')
        :param dns_name: dns_name name managed in Cloud DNS (e.g., 'clusterexpress.com.')
        :param self.dns_name: Cloud DNS zone name (not dns_name, but the zone identifier)
        """
        self.project_id = project_id
        self.region = region
        self.dns_name = f"{dns_name}." # cluster.clusterexpress.com
        self.zone_name = dns_name.replace(".", "-") # cluster.clusterexpress.com
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

    def create_dns_record(
            self,
            ip_address: str,
            ttl: int = 300
    ):
        """
        Create/replace an A record in Cloud DNS pointing to the reserved IP.
        :param record_name: Subdns_name (e.g., 'sims' for sims.clusterexpress.com)
        :param ip_address: Static IP to point to
        :param ttl: Time-to-live (seconds)
        """
        print("===============CREATE DNS RECORD=================")
        try:
            zone = self.check_create_zone()
            if zone is None:
                print(f"Zone {self.dns_name} is None")
                return
            changes = zone.changes()
            records = list(zone.list_resource_record_sets())

            # Check if a matching record already exists
            record_exists = False
            for r in records:
                # The record name from the API is a FQDN (fully qualified dns_name name), so we need to add a dot to our record_name
                if r.name == self.dns_name and r.record_type == "A" and r.rrdatas == [ip_address]:
                    record_exists = True
                    print(f"DNS record with name '{self.dns_name}' and IP '{ip_address}' already exists. Skipping creation.")
                    return

            # If a matching record with a different IP exists, delete it first
            for r in records:
                if r.name == self.dns_name and r.record_type == "A" and r.rrdatas != [ip_address]:
                    print(f"DNS record for '{self.dns_name}' exists with a different IP. Deleting old record.")
                    changes.delete_record_set(r)

            # Add new record
            record_set = zone.resource_record_set(
                self.dns_name,
                "A",
                ttl,
                [ip_address]
            )
            print("add record:", record_set)

            changes.add_record_set(record_set)
            changes.create()
            print(f"✅ DNS record created: {self.dns_name} → {ip_address}")

        except Exception as e:
            print(f"Err create_dns_record: {e}")



    def check_create_zone(self):
        """
        Checks if a DNS zone exists and creates it if it doesn't.
        """
        try:
            # Check if the zone already exists.
            exists, zone = self.get_zone()
            if exists is True:
                print(f"DNS Zone '{self.dns_name}' already exists.")
                return zone
            else:
                raise ValueError("Zone doesnt exists")
        except Exception as e:
            print(f"DNS Zone '{self.dns_name}' not found: {e}")
            # If the zone doesn't exist, create it.
            try:
                self.dns_client.zone(
                    name=self.zone_name,
                    dns_name=self.dns_name
                ).create()
                print("zone created")
                exists, zone = self.get_zone()
                return zone

            except Exception as create_err:
                print(f"Error creating DNS Zone: {create_err}")
                return None


    def get_zone(self):
        zone = self.dns_client.zone(
            name=self.zone_name,
            dns_name=self.dns_name
        )
        print("zone received:", zone)
        # We need to make an API call to actually check its existence.
        exists = zone.exists()
        print(f"zone {zone} exists:", exists)
        return exists, zone




    def delete_dns_record(self, record_name: str):
        """
        Löscht einen A-Record aus Cloud DNS.
        :param record_name: Subdns_name (z.B. 'sims' für sims.clusterexpress.com)
        """
        zone = self.check_create_zone()
        fqdn = f"{record_name}.{self.dns_name}"


        records = list(zone.list_resource_record_sets())
        target_record = None
        for r in records:
            if r.name == fqdn and r.record_type == "A":
                target_record = r
                break

        if not target_record:
            print(f"❌ Kein A-Record gefunden für {fqdn}")
            return

        changes = zone.changes()
        changes.delete_record_set(target_record)
        changes.create()
        print(f"🗑️ DNS record gelöscht: {fqdn}")
