"""
# GET INGRESS
kubectl get service ingress-nginx-controller -n ingress-nginx
"""
import json
import os
import pprint
import time
from tempfile import TemporaryDirectory

from artifact_registry.artifact_admin import ArtifactAdmin
from bm.settings import TEST_USER_ID
from gke_admin.cluster_admin import ClusterManager
from gke_admin.connector import Connector
from gke_admin.core.build_admin import GKEBuildAdmin
from gke_admin.core.cluster_relay import ClusterRelayCreator

from kubernetes import client, config

from gke_admin.core.delete_admin import GKEDestroyer
from gke_admin.core.gke_utils import GKEUtils
from gke_admin.firewall import FirewallManager
from gke_admin.helper.secret_manager import SecretManager
from gke_admin.ingress.ControllerManager import IngressControllerManager
from gke_admin.dns_manager import DNSManager
from gke_admin.ingress_manager import IngressManager
from gke_admin.ip_manager import IPManager
from utils._kubernetes.cert_manager.cert_manager import CertHandler
from utils.file._yaml import write_yaml
from utils.run_subprocess import exec_cmd


class GKEAdmin:

    def __init__(
            self,
            user_id,
            gcp_project_id,
            domain,
            cluster_subdomain,
            cluster_name,
            cluster_port,
            namespace="default",
            region='us-central1',
            app_name=None,
            repo="qfs-repo",
            image="qfs",
            cfg=None,
            cloud="gcp"
    ):
        # ARGS
        self.repo = repo
        self.project_id = gcp_project_id
        self.domain = domain
        self.cluster_subdomain = cluster_subdomain
        self.cluster_port = int(cluster_port)
        self.app_name = app_name
        self.cfg = cfg
        self.region = region
        self.namespace = namespace
        self.cloud = cloud

        self.cluster_name = cluster_name
        self.cluster_domain = f"{cluster_subdomain}.{domain}"
        self.cert_name= f"{self.domain.replace('.','-')}"
        self.ingress_name = f"ingress-{self.cluster_domain.replace('.', '-')}"
        self.backend_cfg_name = f"backendcfg-{self.cluster_domain.replace('.', '-')}"

        self.user_id=user_id

        # AUTH
        self.authenticate_cluster()

        # CLIENTS
        self.client = client.ApiClient()
        self.apps = client.AppsV1Api()
        self.net_api = client.NetworkingV1Api()
        self.core = client.CoreV1Api(self.client)
        self.batch = client.BatchV1Api()
        self.adm = client.AdmissionregistrationV1Api()
        self.configuration = client.Configuration()
        self.networker = client.NetworkingV1Api()
        self.configuration.debug = False

        # CLASSES
        self.file_store = TemporaryDirectory()

        self.artifact_admin = ArtifactAdmin()

        self.ingress_manager = IngressManager(
            self.net_api,
            self.cluster_port,
            self.cluster_domain,
            self.ingress_name,
            self.cert_name,
            self.backend_cfg_name
        )

        self.gke_utils = GKEUtils(
            self.client,
            self.core,
            self.app_name,
            self.cluster_port,
            self.cluster_subdomain,
            self.cluster_domain,
            self.artifact_admin,
            cert_name=self.cert_name,
            ingress_name=self.ingress_name,
            file_store=self.file_store,
            backend_cfg_name=self.backend_cfg_name,
            ingress_manager=self.ingress_manager
        )

        self.cluster_manager = ClusterManager(
            cluster_name=cluster_name,
            region=self.region,
            project_id=gcp_project_id
        )

        self.destroyer = GKEDestroyer(
            self.core,
            self.apps,
            self.batch,
            cert_name=self.cert_name,
        )

        self.dns_manager = DNSManager(
            project_id=gcp_project_id,
            region=self.region,
            dns_name=self.cluster_domain,
            zone_name=self.domain.replace('.','-'),
        )
        self.ip_manager = IPManager(
            self.project_id,
            self.region,
        )

        self.ingress_ctlr_manager = IngressControllerManager(
            self.client,
            self.core,
            self.dns_manager,
            self.apps,
            self.batch,
            self.adm,
        )

        self.secret_manager = SecretManager(
            self.core,
            self.apps,
            self.cluster_domain,
            self.namespace,
            self.cert_name
        )

        self.secret_manager = FirewallManager(
            self.project_id
        )

        self.relay_creator = ClusterRelayCreator(
            self.client,
            self.core,
            self.dns_manager
        )

        self.builder = GKEBuildAdmin(
            self.core,
            self.project_id,
            self.cluster_port,
        )

        self.connector = Connector(
            self.user_id,
            self.project_id,
            self.cluster_domain,
            self.cluster_port,
        )

        self.cert_manager = CertHandler(
            self.core,
            self.apps,
            self.file_store,
            kub_utils=self.gke_utils,
            cert_name=self.cert_name,
            cert_domains=self.cluster_domain
        )


    def authenticate_cluster(self):
        auth_command = f"gcloud container clusters get-credentials {self.cluster_name} --region us-central1 --project aixr-401704"
        exec_cmd(auth_command)
        config.load_kube_config()
        print("Authenticated")


    def deploy(
            self,
            deployment_struct,  # app_name:cfg
    ):

        self.create_connect_infrastructure()

        print("===============START DEPLOYMENT=================")
        # Create DEPL & INGRESS-RULE CFG
        resource_sruct:dict = self.gke_utils.create_resource_cfgs(
            deployment_struct,
        )

        path_struct: dict = self.gke_utils.write_resource_cfgs_to_file_store(
            resource_sruct,
            file_store_name=self.file_store.name
        )

        # CREATE INGRESS SERVICE AND DEPLOYMENT
        active_pods, load_balancer_ip = self.create_resources(path_struct)

        # Create DNS records
        if load_balancer_ip is not None:
            self.dns_manager.create_dns_record(
                ip_address=load_balancer_ip
            )
        print("finished deployment")
        return active_pods


    def create_connect_infrastructure(self):
        print("===============GLOB KUB INFRA=================")

        # CHECK CREATE CLUSTER
        self.cluster_manager.check_cluster_exists()

        # Certificate
        #self.secret_manager.check_create_secret()
        self.cert_manager.handle_cert()

        # GCP HANDLES INGRESS CTLR AND ITS
        #self.handle_ip_config()

    def handle_ip_config(self):
        if self.cluster_manager.auto_cluster is True:
            # todo validate cloud
            service_ip = self.get_gke_ingress_ip_dynamic()
        else:
            print("Deploy resources manually")
            # CONTROLLER (creates its own laodbalancer
            self.ingress_ctlr_manager.check_create_ingress_ctrl()

            # LoadBalancer
            service_ip = self.create_service_process(
                app_name="ingress-nginx-controller",
                namespace="ingress-nginx",
                service_type="LoadBalancer",
            )
        # Create DNS record
        self.dns_manager.create_dns_record(
            ip_address=service_ip
        )
        print("Load Balancer IP config finished")


    def await_ingress_ip(self, ingress_name: str, namespace: str = "default") -> str:
        """
        Waits for a Kubernetes Ingress to get an external IP and returns it.

        Args:
            ingress_name: The name of the Ingress object.
            namespace: The namespace where the Ingress is located.

        Returns:
            The external IP address of the load balancer.
        """
        i=0
        while i<10:
            i += 1
            try:
                ingress = self.networker.read_namespaced_ingress(
                    name=ingress_name,
                    namespace=namespace
                )
                print("ingress found.")
                #pprint.pp(ingress.to_dict())
                # Check if the ingress status has a load balancer ingress list
                if ingress.status and ingress.status.load_balancer and ingress.status.load_balancer.ingress:
                    ip = ingress.status.load_balancer.ingress[0].ip
                    if ip:
                        print(f"Ingress '{ingress_name}' is active. IP: {ip}")
                        return ip

                print(f"Waiting for ingress '{ingress_name}' to be active...")
                time.sleep(3)

            except Exception as e:
                print(f"Err await_ingress_ip: {e}")




    def get_gke_ingress_ip_dynamic(
            self,
            max_retries: int = 10,
            delay_sec: int = 5):
        """
        Retrieves the external IP address of a GKE forwarding rule
        by listing all rules and finding the one created by GKE Ingress.

        Args:
            max_retries: The maximum number of attempts to find the IP.
            delay_sec: The delay in seconds between retries.

        Returns:
            The extracted IP address as a string, or None if not found.
        """
        print("Searching for GKE Ingress IP address...")

        retry_count = 0
        while retry_count < max_retries:
            try:
                command = [
                    "gcloud",
                    "compute",
                    "forwarding-rules",
                    "list",
                    "--format=json"
                ]
                result = exec_cmd(command)
                rules = json.loads(result.stdout)

                for rule in rules:
                    # The GKE Ingress Controller creates forwarding rules whose target is a target pool.
                    # The rule will also have an IP address and use the TCP protocol.
                    # We check for a common pattern to identify it.
                    if "targetPools" in rule.get("target", "") and rule.get("IPAddress"):
                        ip_address = rule["IPAddress"]
                        print(f"IP address found: {ip_address}")
                        return ip_address

            except Exception as e:
                print(f"Err get_gke_ingress_ip_dynamic: {e}")
            time.sleep(delay_sec)
            retry_count += 1

        print(f"Failed to find IP address after {max_retries} attempts.")
        return None



    def create_resources(
            self,
            path_struct: dict
    ):
        """Apply Saved files"""
        print("===============APPLY RESOURCES=================")
        active_pods = []
        load_balancer_ip = None
        for app_name, struct in path_struct.items():
            for rcs_type, path in struct.items():
                ip, rcs_type = self.deploy_rcs(
                    path,
                    rcs_type,
                    app_name
                )
                if ip is not None and rcs_type == "ip":
                    load_balancer_ip = ip
        print("All Resources successfully created -> fielstor cleared")
        return active_pods, load_balancer_ip


    def deploy_rcs(
            self,
            path,
            rcs_type,
            app_name,
    ):
        f_name = path.split('/')[-1].split("\\")[-1]
        print("Deploy File", f_name)
        try:
            self.builder.create_resource_from_yaml(
                file_path=path
            )
            # AWAIT POD STATE ACTIVE
            if rcs_type == "deployment":
                print("await pod deployment")
                pod_names: list = self.gke_utils.await_pod_state([app_name])
                return pod_names, "deployment"
            elif rcs_type == "ingress":
                return self.await_ingress_ip(ingress_name=app_name), "ip"
            print(f"Created resource from: {path}")

        except Exception as e:
            print(f"Error creating resource from path {f_name}: {e}")
        return None, None

    def create_service_process(self, app_name, namespace="default", service_type="LoadBalancer"):
        """
        create_service_process
        """
        print("===============VALIDATE LOAD BALANCER=================")

        print("start create_service_process")
        path = os.path.join(self.file_store.name, f"{service_type}_{app_name}.yaml")
        try:
            service = self.gke_utils.check_service_exists(
                service_name=app_name,
                namespace=namespace
            )
            if service is None:
                print(f"create service {service_type} ")
                self.create_service(
                    app_name,
                    path,
                    service_type
                )
            service_ip = self.await_service_ip(
                app_name,
                namespace
            )
            return service_ip
        except Exception as e:
            print(f"Err create_service_process: {e}")



    def create_service(
            self,
            app_name,
            path,
            service_type
    ):
        content = self.gke_utils.create_service_cfg(
            name=app_name,
        )

        write_yaml(
            content=content,
            dest=path
        )

        self.builder.create_resource_from_yaml(
            file_path=path
        )
        print(f"{service_type} created")

        self.file_store.cleanup()
        print("FileStore cleared")

        service: dict or None = self.gke_utils.check_service_exists(
            service_name=app_name)
        return service



    def await_service_ip(self, app_name, namespace):
        # Start the polling loop
        service_ip = None
        retries = 10  # Maximum number of attempts
        sleep_time = 5  # Seconds to wait between attempts

        for i in range(retries):
            print(f"Checking for LoadBalancer IP... Attempt {i + 1}/{retries}")
            try:
                service: dict or None = self.gke_utils.check_service_exists(
                    service_name=app_name,
                    namespace=namespace
                )

                status = service.get("status", {})
                print("service status", status)

                if service and status.get("load_balancer", {}).get("ingress"):
                    service_ip = status["load_balancer"]["ingress"][0].get("ip")
                    if service_ip:
                        print(f"LoadBalancer IP found: {service_ip}")
                        break
                    time.sleep(sleep_time)

            except Exception as e:
                print(f"Err await_service_ip: {e}")

            time.sleep(sleep_time)
            if retries < i:
                print("Couldnt get service ip")
                break

        return service_ip




if __name__ == "__main__":
    admin = GKEAdmin(
        user_id=TEST_USER_ID,
        gcp_project_id=os.environ["GCP_PROJECT_ID"],
        domain=os.environ["CLUSTER_DOMAIN"],
        cluster_name=os.environ["GKE_SIM_CLUSTER_NAME"],
        cluster_port=os.environ["CLUSTER_PORT"],
        cluster_subdomain=os.environ["CLUSTER_SUB_DOMAIN"],
    )

    # DELETE
    admin.destroyer.cleanup()

    # CERT-MANAGER
    #admin.cert_manager.handle_cert()

    #admin.secret_manager.generate_self_signed_cert_with_san()