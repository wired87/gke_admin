from kubernetes import client


class IngressManager:

    def __init__(
            self,
            api,
            cluster_port,
            cluster_domain,
            ingress_name,
            cert_name,
            backend_cfg_name,
            app_name=None,
    ):
        self.api=api
        self.cluster_domain=cluster_domain
        self.cluster_port=cluster_port
        self.app_name=app_name
        self.cert_name=cert_name
        self.backend_cfg_name=backend_cfg_name
        self.ingress_name = ingress_name

    def get_extend_ingress(self, name: str, rules: list, namespace: str = "default") -> dict or None:
        """
        Check if an Ingress with given name exists.
        If it exists, patch it by adding an annotation 'roles: enabled'.
        If not found, raise Exception.
        """
        try:
            ingress = self.api.read_namespaced_ingress(name=name, namespace=namespace)
            print(f"Ingress '{name}' found.")
            if not ingress:
                print("Create ingress")
                content = self.create_ingress_service_rule(
                    ingress_rules=rules
                )
                return content
            else:

                existing_rules = ingress.spec.rules or []
                existing_rules.extend(client.V1IngressRule(**rule) for rule in rules if rule not in existing_rules)

                body = {
                    "spec": {
                        "rules": existing_rules
                    }
                }

                self.api.patch_namespaced_ingress(name=name, namespace=namespace, body=body)
                print(f"Ingress '{name}' patched with roles annotation.")

        except Exception as e:
            print(f"Ingress '{name}' not found in namespace {namespace}: {e}")

    def create_ingress_service_rule(
            self,
            ingress_rules=None,
    ):
        """
        "nginx.ingress.kubernetes.io/rewrite-target": "/",
        "nginx.ingress.kubernetes.io/proxy-body-size": "50m",
        "nginx.ingress.kubernetes.io/proxy-connect-timeout": "3000",
        "nginx.ingress.kubernetes.io/proxy-read-timeout": "3000",
        "nginx.ingress.kubernetes.io/proxy-send-timeout": "3000",
        "nginx.ingress.kubernetes.io/send-timeout": "3000",
        "nginx.ingress.kubernetes.io/ssl-redirect": "true",
        """
        annotations = {
            "networking.gke.io/managed-certificates": self.cert_name,
            "networking.gke.io/pre-shared-certs": self.cert_name,
            "kubernetes.io/ingress.class": "gce",
            # "kubernetes.io/ingress.global-static-ip-name": load_balancer_ip,
            "cloud.google.com/backend-config": f'{{"default": "{self.backend_cfg_name}"}}'
        }

        print(f"Provice secret {self.cert_name} to ing-rule {self.ingress_name}")
        try:
            ingress_controller = {
                **self.create_pod_metadata(
                    api_version="networking.k8s.io/v1",
                    name=self.ingress_name,
                    labels={},
                    resource_kind="Ingress",  # MultiClusterIngress
                    annotations=annotations
                ),
                "spec": {
                    # "ingressClassName": self.validate_ingress_class,  # gets iggnored > gke 1.18
                    "rules": ingress_rules,
                }
            }
            print("Ingress rule spec created")
            return ingress_controller
        except Exception as e:
            print(f"Err create_ingress_service_rule: {e}")


    def create_ingress_rule(
            self,
            name=None,
            path=None,
            path_type="Prefix"
        ):
        if name is None:
            name = self.app_name

        if path is None:
            path = f"/{name}"

        return {
                "host": self.cluster_domain,
                "http": {
                    "paths": [
                        {
                            "path": path,
                            "pathType": path_type,
                            "backend": {
                                "service": {
                                    "name": name,
                                    "port": {
                                        "number": self.cluster_port
                                    }
                                }
                            }
                        }
                    ]
                }
            }


    def create_pod_metadata(
            self,
            name: str,
            labels: dict = {},
            resource_kind="Deployment",
            annotations={},
            api_version="apps/v1",
    ) -> dict:
        """
        Creates a Kubernetes Pod metadata dictionary.

        Args:
            pod_name: The name of the Pod.
            labels: A dictionary of labels for the Pod.

        Returns:
            A dictionary representing the Pod's API version, kind, and metadata.

        """
        print("create_pod_metadata")
        if name is None:
            name = self.app_name
        return {
            "apiVersion": api_version,
            "kind": resource_kind,
            "metadata": {
                "name": name.replace("_", "-"),
                "labels": labels,
                "annotations": annotations
            }
        }