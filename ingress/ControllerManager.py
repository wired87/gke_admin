
import time

from gke_admin.ip_creator import DNSManager
from utils.run_subprocess import exec_cmd


class IngressControllerManager:

    def __init__(
            self,
            client,
            core,
            ip_manager: DNSManager,
            apps,
            batch,
            adm,
            namespace="ingress-nginx",
            kubeconfig_path=None,
    ):
        self.apps = apps
        self.core = core
        self.batch = batch
        self.adm = adm

        self.client = client
        self.ip_manager = ip_manager
        self.namespace = namespace

        """if kubeconfig_path:
            config.load_kube_config(config_file=kubeconfig_path)
        else:
            try:
                config.load_incluster_config()
            except:
                config.load_kube_config()
        """

    def check_create_ingress_ctrl(self):
        print("===============INGRESS CONTROLLER=================")
        controller_exists = self.check_ingress_controller()

        # INGRESS CONTROLLER
        if controller_exists is False:
            try:
                # CREATE CONTROLLER
                self.create_ingress_controller()

                # AWAIT ACTIVE
                self.wait_for_external_ip()

                admission_ready = self.admission_webhook_ready()
                if admission_ready is False:
                    raise ValueError("Admission Webhook failed")
            except Exception as e:
                print(f"Err check_create_ingress_ctrl: {e}")
                time.sleep(5)
        print("Controller process finished")



    def create_ingress_controller(self):
        try:
            url = "https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.11.3/deploy/static/provider/cloud/deploy.yaml"
            cmd = ["kubectl", "apply", "-f", url]
            exec_cmd(cmd)
            print("Ingress Controler created")
        except Exception as e:
            print(f"Err controller cresation: {e}")


    def wait_for_ingress_nginx_ready(
            self,
            namespace="ingress-nginx",
            timeout=300
    ):
        """
        Wait until ingress-nginx controller and admission webhook are fully ready.
        """



        start = time.time()

        while time.time() - start < timeout:
            # 1. Deployment available
            deploy = self.apps.read_namespaced_deployment("ingress-nginx-controller", namespace)
            if deploy.status.available_replicas != 1:
                print("Waiting for ingress-nginx-controller pod to be available...")
                time.sleep(5)
                continue

            # 2. Jobs finished
            create_job = self.batch.read_namespaced_job("ingress-nginx-admission-create", namespace)
            patch_job = self.batch.read_namespaced_job("ingress-nginx-admission-patch", namespace)
            if not (create_job.status.succeeded and patch_job.status.succeeded):
                print("Waiting for admission jobs to complete...")
                time.sleep(5)
                continue

            # 3. Webhook has CA bundle
            webhook = self.adm.read_validating_webhook_configuration("ingress-nginx-admission")
            ca_bundle = webhook.webhooks[0].client_config.ca_bundle
            if not ca_bundle:
                print("Waiting for admission webhook CA bundle to be patched...")
                time.sleep(5)
                continue

            print("✅ ingress-nginx is fully ready")
            return True

        raise TimeoutError("Timed out waiting for ingress-nginx to be ready")

    def check_ingress_controller(self) -> bool:
        """
        Prüft, ob der nginx Ingress-Controller im Cluster läuft.
        Gibt ein Dict zurück mit Statusinformationen.
        """
        try:
            # Pods im ingress-nginx Namespace
            pods = self.core.list_namespaced_pod(namespace=self.namespace)
            print(f"Pods from  {self.namespace} received")

            if not len(list(pods.items)):
                print("No ingress controller pods fond")
                return False
            print(f"List services in -n {self.namespace}")

            # List Services in ingress-nginx namespace
            svcs = self.core.list_namespaced_service(
                namespace=self.namespace
            )

            for svc in svcs.items:
                name = svc.metadata.name
                if "controller" in name:
                    print(f"Existing ingress controller found")
                    return True

        except Exception as e:
            print(f"Fehler beim Check des Ingress-Controllers: {e}")
        print("No controller could be identified")
        return False



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
        print("⏳ Warte auf externe IP...")
        while time.time() - start < timeout:
            svc = self.core.read_namespaced_service(service_name, self.namespace)
            if svc.status.load_balancer.ingress:
                ip = svc.status.load_balancer.ingress[0].ip
                if ip:
                    print(f"✅ Ingress-Service {service_name} ist aktiv mit IP: {ip}")
                    return ip
            time.sleep(5)
        print("❌ Timeout erreicht – keine externe IP vergeben.")
        return None


    def admission_webhook_ready(
            self,
            namespace="ingress-nginx",
            service_name="ingress-nginx-controller-admission"
    ) -> bool:
        """
        Check if the admission webhook service has at least one ready endpoint.
        Returns True if endpoints exist, False otherwise.
        """
        # load kubeconfig (outside cluster) or incluster (inside pod)
        i = 0
        while i > 10:
            i += 1
            try:
                endpoints = self.core.read_namespaced_endpoints(service_name, namespace)
                print("endpoints", endpoints)
            except Exception as e:
                print(f"Error fetching endpoints: {e}")
                return False

            # loop through subsets and check addresses
            if not endpoints.subsets:
                return False

            for subset in endpoints.subsets:
                if subset.addresses:
                    print(f"Admission webhook ready at: {[a.ip for a in subset.addresses]}")
                    return True
            time.sleep(2)
        return False

