from kubernetes import client, config

# Konfiguriere den Kubernetes-Client
# Dies lädt die Konfiguration aus ~/.kube/config
# oder der Service-Account-Kontext in GKE-Clustern
config.load_kube_config()


class GKEDestroyer:

    def __init__(self):
        self.apps_v1 = client.AppsV1Api()
        self.core_v1 = client.CoreV1Api()
        self.namespace = [
            "default",
            "ingress-nginx"
        ]

    def cleanup(self):
        for namespace in self.namespace:
            print("start cleanup resources")
            self.delete_all_deployments(namespace=namespace)
            self.delete_all_services(namespace=namespace)
            self.delelte_pods(namespace=namespace)
            print("Cleanup completed")

    def delelte_pods(self, pod_names: list[str] = None, all=False, namespace="default"):
        try:
            if all:
                pods = self.core_v1.list_namespaced_pod(namespace=namespace)
                pod_names = [pod.metadata.name for pod in pods.items]

            if pod_names:
                for pn in pod_names:
                    print(f"Working on pod: {pn}")
                    if pn.startswith("env"):
                        self.core_v1.delete_namespaced_pod(name=pn, namespace="default")
                        print(f"Deleted: {pn}")
                    else:
                        print(f"Skipping pod {pn}")
            else:
                print("No pods to delete")
        except client.ApiException as e:
            print(f"Error deleting pods: {e}")

    def force_delete_service(self, service_name: str, namespace: str = "default"):
        """
        Remove finalizers from a Kubernetes Service and force delete it.
        """
        print(f"Attempting to force delete service: {service_name}")
        try:
            # 1. Get the service object
            svc = self.core_v1.read_namespaced_service(name=service_name, namespace=namespace)

            # 2. Check for finalizers and remove them
            if svc.metadata.finalizers:
                print(f"Removing finalizers from service {service_name}")
                # Leere Finalizer-Liste, um sie zu entfernen
                svc.metadata.finalizers = []
                self.core_v1.patch_namespaced_service(name=service_name, namespace=namespace, body=svc)
                print(f"Finalizers removed from service {service_name}.")
            else:
                print(f"No finalizers found in {service_name}")

            # 3. Force delete the service
            self.core_v1.delete_namespaced_service(
                name=service_name,
                namespace=namespace,
                grace_period_seconds=0,
                orphan_dependents=False
            )
            print(f"Service {service_name} force-deleted successfully.")

        except client.ApiException as e:
            if e.status == 404:
                print(f"Service {service_name} not found.")
            else:
                print(f"Error force deleting service: {e}")

    def delete_all_services(self, namespace: str = "default"):
        """
        Löscht alle Services im angegebenen Namespace (außer dem 'kubernetes'-Service).
        """
        try:
            services = self.core_v1.list_namespaced_service(namespace=namespace)
            services_to_delete = [s.metadata.name for s in services.items if s.metadata.name != "kubernetes"]

            if not services_to_delete:
                print(f"Keine Services im Namespace '{namespace}' gefunden (außer dem Standard 'kubernetes').")
                return

            for svc in services_to_delete:
                print(f"Deleting service '{svc}'...")
                try:
                    self.core_v1.delete_namespaced_service(name=svc, namespace=namespace)
                    print(f"Service '{svc}' successfully initiated deletion.")
                except client.ApiException as e:
                    if e.status == 409:  # Conflict status code
                        print(f"Deletion of service '{svc}' is hanging. Forcing deletion...")
                        self.force_delete_service(service_name=svc, namespace=namespace)
                    else:
                        print(f"Error deleting service '{svc}': {e}")
            print("All services processed.")
        except client.ApiException as e:
            print(f"Error getting services: {e}")

    def delete_all_deployments(self, namespace: str = "default"):
        """
        Löscht alle Deployments im angegebenen Namespace, inkl. aller Pods.
        """
        try:
            deployments = self.apps_v1.list_namespaced_deployment(namespace=namespace)
            if not deployments.items:
                print(f"Keine Deployments im Namespace '{namespace}' gefunden.")
                return

            for dep in deployments.items:
                name = dep.metadata.name
                print(f"Deleting deployment '{name}'...")
                self.apps_v1.delete_namespaced_deployment(name=name, namespace=namespace)
                print(f"Deployment '{name}' deleted.")
        except client.ApiException as e:
            print(f"Error deleting deployments: {e}")