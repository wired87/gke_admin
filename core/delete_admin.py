from kubernetes import client

class GKEDestroyer:

    def __init__(self, core, apps, batch, cert_name):
        self.apps = apps
        self.core = core
        self.batch=batch
        self.api = client.NetworkingV1Api()
        self.admin_reg_api = client.AdmissionregistrationV1Api()

        self.cert_name = cert_name
        self.namespace = [
            "default",
            "ingress-nginx",
            "cert-manager"
        ]


    def cleanup_completed_jobs(self, namespace: str = "default"):
        """
        Lists all completed Jobs in a given namespace and deletes them.

        Args:
            namespace: The namespace to clean up. Defaults to "default".
        """
        print(f"🕵️ Listing jobs in namespace '{namespace}'...")
        try:
            jobs = self.batch.list_namespaced_job(namespace=namespace)
            print(f"Found {len(jobs.items)} jobs. 🧐")

            deleted_count = 0
            for job in jobs.items:
                job_name = job.metadata.name
                # Check if the job has completed successfully
                if job.status.succeeded is not None and job.status.succeeded > 0:
                    print(f"Found completed job: {job_name}. 🗑️ Deleting...")
                    self.batch.delete_namespaced_job(
                        name=job_name,
                        namespace=namespace,
                        body=client.V1DeleteOptions(propagation_policy="Background")
                    )
                    deleted_count += 1
                else:
                    print(f"Skipping job: {job_name}. Status: Not completed. 🚧")

            print(f"✅ Cleanup complete. Deleted {deleted_count} completed jobs.")

        except client.ApiException as e:
            print(f"❌ An API error occurred: {e}")

    # Example usage:
    # cleanup_completed_jobs(namespace="ingress-nginx")






    def delete_validating_webhook_configurations(
            self,
            name_contains: str = "nginx"
    ):
        """
        Deletes ValidatingWebhookConfiguration resources whose names contain the specified string.

        Args:
            name_contains: The substring to search for in webhook names (e.g., "nginx").
        """

        try:
            webhooks = self.admin_reg_api.list_validating_webhook_configuration()
            print(f"Found {len(webhooks.items)} validating webhook configurations.")
            found_match = False
            for webhook in webhooks.items:
                name = webhook.metadata.name
                if name_contains in name:
                    print(f"Found and deleting webhook: {webhook.metadata.name}")
                    self.admin_reg_api.delete_validating_webhook_configuration(name=webhook.metadata.name)
                    found_match = True

            if not found_match:
                print(f"No webhook configurations found with '{name_contains}' in the name.")

        except client.ApiException as e:
            print(f"An error occurred: {e}")

    # Example usage:
    # delete_validating_webhook_configurations(name_contains="nginx")



    def cleanup(self):
        for namespace in self.namespace:
            print("start cleanup resources")
            self.delete_all_deployments(namespace=namespace)
            self.delete_all_services(namespace=namespace)
            self.delelte_pods(namespace=namespace)
            self.delete_ingress(namespace)
            self.delete_secret(cert_name=self.cert_name, namespace=namespace)
            self.delete_validating_webhook_configurations()
            self.cleanup_completed_jobs()
            print("Cleanup completed")

    def delete_secret(
            self,
            cert_name: str,
            namespace: str = "default"
    ):
        print("delete secret")
        """
        Löscht ein Secret im angegebenen Namespace.
        Nutzt den Kubernetes Python Client (CoreV1Api).
        """
        try:
            self.core.delete_namespaced_secret(
                name=cert_name,
                namespace=namespace
            )
            print(f"🗑️ Secret '{cert_name}' im Namespace '{namespace}' gelöscht.")
        except Exception as e:
            print(f"⚠️ Secret '{cert_name}' im Namespace '{namespace}' nicht gefunden: {e}")
        
    def delete_ingress(self, namespace):
        try:
            ingress_list = self.api.list_namespaced_ingress(namespace=namespace)
            if not ingress_list.items:
                print(f"✅ Keine Ingresses im Namespace '{namespace}' gefunden.")
                return

            for ingress in ingress_list.items:
                name = ingress.metadata.name
                try:
                    self.api.delete_namespaced_ingress(name=name, namespace=namespace)
                    print(f"🗑️  Ingress '{name}' deleted from -n '{namespace}'")
                except Exception as e:
                    print(f"⚠️ Fehler beim Löschen von Ingress '{name}': {e}")

        except Exception as e:
            print(f"❌ Fehler beim Auflisten von Ingresses: {e}")



    def delelte_pods(self, pod_names: list[str] = None, all=False, namespace="default"):
        try:
            if all:
                pods = self.core.list_namespaced_pod(namespace=namespace)
                pod_names = [pod.metadata.name for pod in pods.items]

            if pod_names:
                for pn in pod_names:
                    print(f"Working on pod: {pn}")
                    if pn.startswith("env"):
                        self.core.delete_namespaced_pod(name=pn, namespace="default")
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
            svc = self.core.read_namespaced_service(name=service_name, namespace=namespace)

            # 2. Check for finalizers and remove them
            if svc.metadata.finalizers:
                print(f"Removing finalizers from service {service_name}")
                # Leere Finalizer-Liste, um sie zu entfernen
                svc.metadata.finalizers = []
                self.core.patch_namespaced_service(name=service_name, namespace=namespace, body=svc)
                print(f"Finalizers removed from service {service_name}.")
            else:
                print(f"No finalizers found in {service_name}")

            # 3. Force delete the service
            self.core.delete_namespaced_service(
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
            services = self.core.list_namespaced_service(namespace=namespace)
            services_to_delete = [s.metadata.name for s in services.items if s.metadata.name != "kubernetes"]

            if not services_to_delete:
                print(f"Keine Services im Namespace '{namespace}' gefunden (außer dem Standard 'kubernetes').")
                return

            for svc in services_to_delete:
                print(f"Deleting service '{svc}'...")
                try:
                    self.core.delete_namespaced_service(name=svc, namespace=namespace)
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
            deployments = self.apps.list_namespaced_deployment(namespace=namespace)
            if not deployments.items:
                print(f"Keine Deployments im Namespace '{namespace}' gefunden.")
                return

            for dep in deployments.items:
                name = dep.metadata.name
                print(f"Deleting deployment '{name}'...")
                self.apps.delete_namespaced_deployment(name=name, namespace=namespace)
                print(f"Deployment '{name}' deleted.")
        except client.ApiException as e:
            print(f"Error deleting deployments: {e}")