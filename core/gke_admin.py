"""
# GET INGRESS
kubectl get service ingress-nginx-controller -n ingress-nginx
"""

import os
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
from gke_admin.ingress.ControllerManager import IngressControllerManager
from gke_admin.ip_creator import DNSManager
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
            app_name=None,
            repo="qfs-repo",
            image="qfs",
            cfg=None,
    ):
        # ARGS
        self.repo = repo
        self.project_id = gcp_project_id
        self.domain = domain
        self.cluster_subdomain = cluster_subdomain
        self.cluster_port = int(cluster_port)
        self.app_name = app_name
        self.cfg = cfg
        self.region = 'us-central1'

        self.cluster_name = cluster_name
        self.cluster_domain = f"{cluster_subdomain}.{domain}"
        print("CLUSTER DOMAIN:", self.cluster_domain)

        self.user_id=user_id

        # AUTH
        self.authenticate_cluster()

        # CLIENTS
        self.client = client.ApiClient()
        self.core = client.CoreV1Api(self.client)
        self.configuration = client.Configuration()
        self.configuration.debug = False


        self.artifact_admin = ArtifactAdmin()

        self.gke_utils = GKEUtils(
            self.client,
            self.core,
            self.app_name,
            self.cluster_port,
            self.cluster_subdomain,
            self.cluster_domain,
            self.artifact_admin,
        )

        # CLASSES
        self.cluster_manager = ClusterManager(
            cluster_name=cluster_name,
            region=self.region,
            project_id=gcp_project_id
        )

        self.destroyer = GKEDestroyer()

        self.ip_manager = DNSManager(
            project_id=gcp_project_id,
            region=self.region,
            dns_name=self.cluster_domain,
        )

        self.ingress_ctlr_manager = IngressControllerManager(
            self.client,
            self.core,
            self.ip_manager
        )
        self.relay_creator = ClusterRelayCreator(
            self.client,
            self.core,
            self.ip_manager
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

        self.file_store = TemporaryDirectory()


    def authenticate_cluster(self):
        auth_command = f"gcloud container clusters get-credentials {self.cluster_name} --region us-central1 --project aixr-401704"
        exec_cmd(auth_command)
        config.load_kube_config()
        print("Authenticated")


    def deploy(
            self,
            deployment_struct,  # app_name:cfg
    ):
        print("deploy:", deployment_struct)

        # Make deployment available to the web
        self.create_connect_infrastructure()

        # Create DEPL & INGRESS-RULE CFG
        resource_sruct:dict = self.gke_utils.create_resource_cfgs(deployment_struct)

        resource_paths: list[str] = self.gke_utils.write_resource_cfgs_to_file_store(
            resource_sruct,
            file_store_name=self.file_store.name
        )

        # CREATE INGRESS SERVICE AND DEPLOYMENT
        self.create_resources(resource_paths)

        # Await resirces alive
        active_pods = self.gke_utils.await_pod_state(
            list(deployment_struct.keys())
        )
        return active_pods




    def create_connect_infrastructure(self):
        # CHECK CREATE CLUSTER
        self.cluster_manager.check_cluster_exists()

        # CONTROLLER (creates its own laodbalancer
        self.ingress_ctlr_manager.check_create_ingress_ctrl()

        # Certificate
        self.builder.build_managed_certificate()

        # LoadBalancer
        self.create_service_process(
            app_name="ingress-nginx-controller",
            namespace="ingress-nginx",
            service_type="LoadBalancer",
        )


    def create_resources(
            self,
            paths:list[str]
    ) -> list:
        """Apply Saved files"""
        for path in paths:
            f_name = path.split('/')[-1].split("\\")[-1]
            print("Deploy File", f_name)
            try:
                self.builder.create_resource_from_yaml(
                    file_path=path
                )
                print(f"Created resource from: {path}")
            except Exception as e:
                print(f"Error creating resource from path {f_name}: {e}")
        print("All Resources successfully created -> fielstor cleared")



    def create_service_process(self, app_name, namespace="default", service_type="LoadBalancer"):
        """
        create_service_process
        """
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

            # Create DNS record
            self.ip_manager.create_dns_record(
                ip_address=service_ip
            )
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