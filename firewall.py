from google.cloud import compute_v1

class FirewallManager:
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.client = compute_v1.FirewallsClient()

    def create_ingress_firewall_rule(
        self,
        rule_name: str,
        source_ranges: list[str],
        ports: list[str],
        target_tags: list[str] = None
    ):
        """
        Creates a firewall rule to allow traffic from specified IP ranges to target tags.

        Args:
            rule_name: The name for the new firewall rule.
            source_ranges: A list of CIDR IP ranges to allow.
            ports: A list of ports to open.
            target_tags: A list of network tags to apply the rule to.
        """
        print(f"Creating firewall rule '{rule_name}'... 🛠️")

        firewall_rule = compute_v1.Firewall(
            name=rule_name,
            direction="INGRESS",
            priority=1000,
            allowed=[
                compute_v1.Allowed(
                    ip_protocol="tcp",
                    ports=ports,
                )
            ],
            source_ranges=source_ranges,
            target_tags=target_tags
        )

        operation = self.client.insert(
            project=self.project_id,
            firewall_resource=firewall_rule
        )

        operation.wait()

        print(f"✅ Firewall rule '{rule_name}' created successfully.")

# Example usage:
# firewall_manager = FirewallManager(project_id="my-gcp-project")
# firewall_manager.create_ingress_firewall_rule(
#     rule_name="allow-gke-health-checks",
#     source_ranges=["130.211.0.0/22", "35.191.0.0/16"],
#     ports=["80", "8080", "8001"]
# )