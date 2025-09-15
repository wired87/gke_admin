import os
from tempfile import TemporaryDirectory

from artifact_registry.artifact_admin import ArtifactAdmin
from bm.settings import TEST_USER_ID
from fb_core.real_time_database import FirebaseRTDBManager
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
            cluster_domain,
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
        self.cluster_domain = cluster_domain
        self.cluster_subdomain = cluster_subdomain
        self.cluster_port = int(cluster_port)
        self.app_name = app_name
        self.cfg = cfg
        self.region = 'us-central1'
        self.cluster_name = cluster_name

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

        self.destroyer = GKEDestroyer(
            self.gke_utils
        )

        self.ip_manager = DNSManager(
            gcp_project_id,
            self.region,
            cluster_domain,
            dns_zone=f"{cluster_domain.split('.')[0]}-zone"
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
            self.cluster_domain,
            self.cluster_port,
            self.cluster_subdomain
        )

        self.connector = Connector(
            self.user_id,
            self.project_id,
            self.cluster_domain,
            self.cluster_name,
            self.cluster_port,
            self.cluster_subdomain,
        )

        self.file_store = TemporaryDirectory()


    def authenticate_cluster(self):
        auth_command = f"gcloud container clusters get-credentials {self.cluster_name} --region us-central1 --project aixr-401704"
        exec_cmd(auth_command)
        config.load_kube_config()
        print("Authenticated")


    def deploy(
            self,
            deployment_struct, # app_name:cfg
    ):
        # Make deployment available to the web
        self.create_connect_infrastructure()

        # Create DEPL & INGRESS-RULE CFG
        resource_struct:dict = self.gke_utils.create_resource_cfgs(deployment_struct)

        resource_paths: list[str] = self.gke_utils.write_resource_cfgs_to_file_store(
            resource_struct,
            file_store_name=self.file_store.name
        )

        # CREATE INGRESS SERVICE AND DEPLOYMENT
        self.create_resources(resource_paths)

        # Await resirces alive
        self.gke_utils.await_pod_state(
            list(deployment_struct.keys())
        )




    def create_connect_infrastructure(self):
        # CHECK CREATE CLUSTER
        self.cluster_manager.check_cluster_exists()

        # CONTROLLER
        self.ingress_ctlr_manager.check_create_ingress_ctrl()

        # Certificate
        self.builder.build_managed_certificate()

        # LoadBalancer
        self.create_service_process(
            app_name="load-balancer",
            service_type="LoadBalancer",
        )


    def create_resources(
            self,
            paths:list[str]
    ) -> list:
        """Apply Saved files"""
        for path in paths:
            print("Deploy File", path)
            try:
                self.builder.create_resource_from_yaml(
                    file_path=path
                )
                print(f"Created resource from: {path}")
            except Exception as e:
                print(f"Error creating resource from path {path}: {e}")
        print("All Resources successfully created -> fielstor cleared")



    def create_service_process(self, app_name, service_type="LoadBalancer"):
        """
        create_service_process
        """
        path = os.path.join(self.file_store.name, f"{service_type}_{app_name}.yaml")

        service = self.gke_utils.check_service_exists(
            service_name=app_name)
        if service is not None:
            print(f"Service {service_type} already exists")
            return

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

        service = self.gke_utils.check_service_exists(
            service_name=app_name)
        """
        status:
          loadBalancer:
            ingress:
              - ip: 34.41.41.191
        """
        service_ip = service["status"]["loadBalancer"]["ingress"][0]
        if service_ip is None:
            raise ValueError("No ip in service found")

        # Create DNS record
        self.ip_manager.create_dns_record(
            record_name=f"{self.cluster_subdomain}-{self.cluster_domain.replace('.', '-')}",
            ip_address=service_ip
        )








if __name__ == "__main__":
    admin = GKEAdmin(
        user_id=TEST_USER_ID,
        gcp_project_id=os.environ["GCP_PROJECT_ID"],
        cluster_domain=os.environ["CLUSTER_DOMAIN"],
        cluster_name=os.environ["GKE_SIM_CLUSTER_NAME"],
        cluster_port=os.environ["CLUSTER_PORT"],
        cluster_subdomain=os.environ["CLUSTER_SUB_DOMAIN"],
    )
    # DELETE
    admin.destroyer.cleanup()