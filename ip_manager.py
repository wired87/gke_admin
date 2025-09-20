from __future__ import annotations

from google.cloud import compute_v1


class IPManager:
    def __init__(self, project_id: str, region: str):
        self.project_id = project_id
        self.region = region
        self.ip_client = compute_v1.AddressesClient()


    def check_create_ip(self, ip_name: str) -> str:
        existing_ip: str or None = self.get_ip_by_name(ip_name)
        if existing_ip is None:
            existing_ip = self.reserve_static_ip(ip_name)
        return existing_ip


    def get_ip_by_name(self, name: str) -> str | None:
        """
        Gets a reserved IP address by name and returns its IP string.
        Returns None if the IP is not found.
        """
        try:
            address = self.ip_client.get(
                project=self.project_id,
                region=self.region,
                address=name
            )
            ip = address.address
            print(f"✅ Existing ip: {ip}")
            return ip
        except Exception as e:
            print("No IP could be found:", e)
            return None

    def reserve_static_ip(self, name: str) -> str:
        """
        Reserves a static external IP address in the given region.
        :param name: Name for the reserved IP (e.g., 'my-ingress-ip')
        :return: IP address as string
        """
        try:
            address_resource = compute_v1.Address(name=name)

            print(f"Reserving static IP '{name}'...")

            # Insert the new address and wait for the operation to complete
            operation = self.ip_client.insert(
                project=self.project_id,
                region=self.region,
                address_resource=address_resource
            )

            #operation.done()

            # Fetch the created IP address to get its string value
            address = self.ip_client.get(
                project=self.project_id,
                region=self.region,
                address=name
            )

            print(f"✅ IP address '{name}' reserved with value: {address.address}")
            return address.address
        except Exception as e:
            print("Error reserving static IP:", e)
    def delete_ip(self, name: str):
        """
        Deletes a reserved IP by its name.
        """
        existing_ip: str | None = self.get_ip_by_name(name)
        if existing_ip is None:
            print(f"No Ip specified under {name}")
            return

        print(f"Deleting IP {name}")

        operation = self.ip_client.delete(
            project=self.project_id,
            region=self.region,
            address=name
        )
        # Wait for the operation to complete
        operation.wait()

        print(f"🗑️ Statische IP {name} gelöscht.")