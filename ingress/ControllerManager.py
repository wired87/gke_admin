import pprint
import time
from kubernetes import config

from gke_admin.ip_creator import IPManager
from utils.run_subprocess import exec_cmd


class IngressControllerManager:

    def __init__(
            self,
            client,
            ip_manager: IPManager,
            namespace="ingress-nginx",
            kubeconfig_path=None,
    ):
        self.client = client
        self.ip_manager = ip_manager
        self.namespace = namespace

        if kubeconfig_path:
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            try:
                config.load_incluster_config()
            except:
                config.load_kube_config()


    def check_create_ingress_ctrl(self):
        print("Check for ingress controlelr")
        status = self.check_ingress_controller()

        # INGRESS CONTROLLER
        if not status["installed"]:
            self.controller_creation_process()
        print("Ingress already created ingress controlelr")


    def controller_creation_process(self):
        print("Install ingress controlelr")

        # CREATE CONTROLLER
        self.create_ingress_controller()

        # AWAIT ACTIVE
        controller_ip = self.wait_for_external_ip()

        # DELETE OLD INGRESS IP IF EXISTS
        self.ip_manager.delete_ip(
            name=self.namespace
        )

        # SAVE CTL IP
        self.ip_manager.save_existing_ip(
            ip=controller_ip,
            ip_name=self.namespace,
        )
        print("Controller process finished")



    def create_ingress_controller(self):
        try:
            url = "https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/cloud/deploy.yaml"
            cmd = ["kubectl", "apply", "-f", url]
            result = exec_cmd(cmd)
            print("Ingress Controler created:", result)
        except Exception as e:
            print(f"Controller cresation error: {e}")


    def check_ingress_controller(self) -> dict:
        """
        Prüft, ob der nginx Ingress-Controller im Cluster läuft.
        Gibt ein Dict zurück mit Statusinformationen.
        """
        result = {
            "installed": False,
            "pods": [],
            "services": [],
        }

        try:
            # Pods im ingress-nginx Namespace
            pods = self.client.list_namespaced_pod(namespace="ingress-nginx")
            result["pods"] = [p.status.phase for p in pods.items]

            # List Services in ingress-nginx namespace
            svcs = self.client.list_namespaced_service(
                namespace="ingress-nginx"
            )
            result["services"] = [s.metadata.name for s in svcs.items]

            # Mark installed if controller service exists
            if any("ingress-nginx-controller" in s for s in result["services"]):
                result["installed"] = True

        except Exception as e:
            print(f"Fehler beim Check des Ingress-Controllers: {e}")

        print("Ingress-Controller-Check Ergebnis:")
        pprint.pp(result)
        return result



    def wait_for_external_ip(
            self,
            service_name="ingress-nginx-controller",
            timeout=300
    ):
        """
        Wartet, bis der Ingress-Service eine externe IP erhalten hat.
        :param service_name: Name des Ingress-Services
        :param timeout: Max. Zeit in Sekunden
        :return: Externe IP oder None
        """
        start = time.time()
        while time.time() - start < timeout:
            svc = self.core.read_namespaced_service(service_name, self.namespace)
            if svc.status.load_balancer.ingress:
                ip = svc.status.load_balancer.ingress[0].ip
                if ip:
                    print(f"✅ Ingress-Service {service_name} ist aktiv mit IP: {ip}")
                    return ip
            print("⏳ Warte auf externe IP...")
            time.sleep(5)
        print("❌ Timeout erreicht – keine externe IP vergeben.")
        return None