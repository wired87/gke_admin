from utils.run_subprocess import exec_cmd


class GKEDestroyer:

    def __init__(self, gke_utils):
        self.gke_utils=gke_utils

    def cleanup(self):
        self.delete_all_deployments()
        self.delete_all_services()
        self.delelte_pods()


    def delelte_pods(self, pod_names:list[str]=None, all=False):
        # Löschbefehl für den Pod
        if all is True:
            pod_names = self.gke_utils.get_pods()

        if pod_names is not None:
            for pn in pod_names:
                print(f"Working del equest or pod: {pn}")
                if pn.startswith("env"):
                    cmd = ['kubectl', 'delete', 'pod', pn]
                    exec_cmd(cmd)
                    print(f"Deleted: {pn}")
                else:
                    print(f"Skipping pod {pn}")
        else:
            print("No pods to delete")
        print("Pod names deleted")


    def delete_all_services(self, namespace: str = "default"):
        """
        Löscht alle Services im angegebenen Namespace (außer dem 'kubernetes'-Service).
        """
        # Alle Service-Namen holen
        cmd = ["kubectl", "get", "svc", "-n", namespace, "-o", "jsonpath={.items[*].metadata.name}"]
        result = exec_cmd(cmd)
        if result is not None:
            services = result.strip().split()

            # Standard-Service rausfiltern
            services = [svc for svc in services if svc != "kubernetes"]

            if not services:
                print(f"Keine Services im Namespace '{namespace}' gefunden (außer dem Standard 'kubernetes').")
                return

            for svc in services:
                cmd = ["kubectl", "delete", "svc", svc]
                exec_cmd(cmd)
                print(f"Service '{svc}' gelöscht.")
        else:
            print("Error del all services cmd ")
        print("Alle Services erfolgreich gelöscht.")

    def delete_all_deployments(self, namespace: str = "default"):
        """
        Löscht alle Deployments im angegebenen Namespace, inkl. aller Pods.
        """
        # Alle Deployment-Namen holen
        cmd = ["kubectl", "get", "deployments", "-n", namespace, "-o", "jsonpath={.items[*].metadata.name}"]
        result = exec_cmd(cmd)
        if result is not None:
            deployments = result.strip().split()

            if not deployments:
                print(f"Keine Deployments im Namespace '{namespace}' gefunden.")
                return

            for dep in deployments:
                cmd = ["kubectl", "delete", "deployment", dep]
                exec_cmd(cmd)
                print(f"Deployment '{dep}' inkl. Pods gelöscht.")
        print("Alle Deployments erfolgreich gelöscht.")

