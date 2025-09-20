import os
import subprocess
import time
from kubernetes import client, config

from utils._kubernetes import MANAGED_CERTIFICATE_PATH
from utils.file._yaml import write_yaml
from utils.run_subprocess import exec_cmd

import dotenv
dotenv.load_dotenv()

class GKEBuildAdmin(

):
    def __init__(
            self,
            core,
            gcp_project_id,
            cluster_port,
            app_name=None,
            repo="qfs-repo", 
            image="qfs", 
            cfg=None, 
    ):
        # IMAGE COMPONENTS
        self.app_name = app_name
        self.cfg = cfg
        self.core = core

        self.repo = repo

        self.project_id = gcp_project_id

        self.cluster_port = int(cluster_port)

        # RAY cluster image
        self.image = image
        self.tag = "latest"

        self.full_tag = None

    ################################### YAML


    def create_deployments_process(self, env_cfg:dict) -> dict:
        print(f"create_deployments_process env_cfg")

        try:
            # GET DEPLOYMENT COMMANDS
            env_cfg = self.get_depl_cmd(env_cfg)

            # CREATE DEPLOYMENTS
            self.create_deployments(env_cfg)

            # update env_cfg with pod_name
            env_cfg:dict = self.get_pod_names(env_cfg)

            # SET VM/POD SPECS
            self.set_pod_vm_spacs_cmd(env_cfg)

            # EXPOSE DEPLOYMENTS
            for env_id, struct in env_cfg.items():
                self.expose_deployment(
                    deployment_name=struct["deployment"]["name"],
                    service_name=struct["deployment"]["name"],
                    port=self.cluster_port,
                    target_port=self.cluster_port,
                )
            print("Deployment process finished.Updated env_cfg.")

        except Exception as e:
            print(f"Exception while create_deployments_process: {e}")

        finally:
            print("GKE create_deployments_process process finalized.")

        return env_cfg


    def create_resource_from_yaml(self, file_path: str):
        """
        Creates a Kubernetes Pod from a given YAML file.
        """
        cmd = ['kubectl', 'apply', '-f', file_path]
        print(f"create_resource_from_yaml from cmd {cmd}")

        result = exec_cmd(cmd)

        if result is not None:
            print(f"Resource was successfully created from '{file_path}'.")
        else:
            raise ValueError("Failed create_resource_from_yaml")



    def get_nginx_controller(self):
        cmd = [
            "kubectl", "get", "ingress", "--all-namespaces", "-o",
            "jsonpath={range .items[*]}{.metadata.namespace}:{.metadata.name}{\"\\n\"}{end}"
        ]
        result = exec_cmd(cmd)
        return result



    ########### CMD ##########################

    def get_pod_info(self, pod_name, namespace):
        try:
            pod_details = self.core.read_namespaced_pod(
                name=pod_name,
                namespace=namespace,
            )
            print("Pod details successfully retrieved:")
            #print(pod_details.to_dict())
            return pod_details.to_dict()
        except client.ApiException as e:
            print(f"Error retrieving pod details: {e}")





    def build_secrets(self, env_dict: dict) -> list:
        # SET SECRETS
        secrets = ["--update-secrets"]
        for key, val in env_dict.items():
            secrets.append(f"{key}={val},")
        return secrets




    def get_img_tag(self):
        return f"{self.region}-docker.pkg.dev/{self.project_id}/{self.repo}/{self.image_name}:{self.tag}"



    def create_deployment_with_images_cmd(self, env_id, cfg_struct):
        # 1. Base Deployment mit allen images erstellen
        secret_name = cfg_struct["deployment"]["secret_name"]
        create_cmd = [
            "kubectl",
            "create",
            "deployment",
            env_id,
            "--image",
            self.get_img_tag(),
            f"--from-secret=secret-name={secret_name}"
        ]
        return create_cmd


    def expose_deployment(
            self,
            deployment_name: str,
            service_name: str,
            port: int = 80,  # cluster requests
            target_port: int = 8080,  # extern requests
            namespace: str = "default"
    ):
        """
        Expose ein Deployment als Service (LoadBalancer).
        """
        cmd = (
            f"kubectl expose deployment {deployment_name} "
            f"--name={service_name} "
            f"--type=LoadBalancer "
            f"--port={port} "
            f"--target-port={target_port} "
            f"--namespace={namespace}"
        )
        exec_cmd(cmd)
        print(f"Deployment '{deployment_name}' exposed as Service '{service_name}' on port {port}->{target_port}")

    def set_env_cmd(self, env_id, env_vars:dict):
        """
        Erstellt für jede env_id einen Stack und setzt die Umgebungsvariablen.
        """
        env_vars_list = [f"{key}={value}" for key, value in env_vars.items()]
        set_env_cmd = ["kubectl", "set", "env", env_id] + env_vars_list
        return set_env_cmd

    def set_pod_vm_spacs_cmd(self, env_cfg):
        for env_id, struct in env_cfg.items():
            try:
                depl_name = struct["deployment"]["name"] # depl name
                set_res_cmd = [
                    "kubectl",
                    "set",
                    "resources",
                    f"deployment/{depl_name}",
                    "--requests=cpu=4",
                    "--requests=memory=16Gi",
                    "--limits=cpu=16",
                    "--limits=memory=25Gi",
                    "-c",
                    self.image_name
                ]
                exec_cmd(
                    cmd=set_res_cmd
                )
            except Exception as e:
                print(f"Exception while set_pod_vm_spacs_cmd: {e}")
        print("Specs for all pods set")

    def get_pod_ip(self, pod_name: str, namespace: str = "default") -> str:
        config.load_kube_config()  # nutzt ~/.kube/config nach get-credentials
        v1 = client.CoreV1Api()
        pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
        return pod.status.pod_ip




    def add_pod_names_world_cfgs(self, world_cfgs):
        pod_identifiers = {}
        pod_names = []
        for env_id, creation_cmd in world_cfgs.items():
            all_pods = self.get_pods()
            if all_pods is not None:
                for pod in list(all_pods):
                    if pod.startswith(pod) and env_id not in pod_identifiers:
                        world_cfgs[env_id]["pod_name"] = pod
                        pod_names.append(pod)
        print(f"envcfg updated with pod names")
        return world_cfgs, pod_names



    def create_deployments(self, env_cfg):
        for env_id, struct in env_cfg.items():
            # erst YAML erzeugen (dry-run) und dann apply
            cmd = struct["deployment"]["command"] + ["--dry-run=client", "-o", "yaml"]
            p1 = exec_cmd(cmd)
            if p1 is not None:
                cmd =["kubectl", "apply", "-f", "-"]
                exec_cmd(cmd, inp=p1)



    def wait_for_external_ip(
            self,
            service_name,
            namespace="default",
            timeout=300,
    ):
        v1 = client.CoreV1Api()
        for _ in range(timeout // 5):
            svc = v1.read_namespaced_service(service_name, namespace)
            ingress = svc.status.load_balancer.ingress
            if ingress:
                return ingress[0].ip or ingress[0].hostname
            time.sleep(5)
        return None



    def get_service_public_ips(
            self,
            service_names:list,
            namespace="default",
    ) -> dict:
        """
        Returns {service_name: external_ip or None} for all services in a namespace
        using the official Kubernetes Python client.
        """
        def extract_ip(ingress):
            ip = ingress[0].ip or ingress[0].hostname
            if "pending" in ip:
                time.sleep(2)
                ip = extract_ip()
            print(f"IP extracted: {ip}")
            return ip

        print("Extracting Extern IPs")
        services = self.core.list_namespaced_service(
            namespace=namespace
        )

        result = {}
        for sn in service_names:
            for svc in services.items:
                name = svc.metadata.name
                print(f"Extract IP from {sn} for {name}")
                if name.startswith(sn) or sn.strip() == name.strip():
                    ip = self.wait_for_external_ip(
                        service_name=name
                    )
                    result[name] = ip
                else:
                    print(f"Skip IP extraction for {name}")
        print("Finished IP Extraction")
        #pprint.pp(result)
        return result

    def get_depl_cmd(self, env_cfg:dict):
        try:
            for env_id, struct in env_cfg.items():
                print(F"Create depl cmd rom struct:")
                #pprint.pp(struct)

                conv_env_id = env_id.replace('_', '-')

                struct["deployment"]["command"] = self.create_deployment_with_images_cmd(
                    env_id=conv_env_id,
                    cfg_struct=struct
                )
                struct["deployment"]["name"] = conv_env_id
            print("Deployment CMDs created")
            return env_cfg
        except Exception as e:
            print(f"Exception while get_depl_cmd: {e}")

        finally:
            print("GKE get_depl_cmd process finalized.")

    def build_managed_certificate(self):
        """
        Creates a certificate for ingress rules
        """
        try:
            self.create_resource_from_yaml(
                MANAGED_CERTIFICATE_PATH
            )
            print("Certificate created")
        except Exception as e:
            print(f"Err build_managed_certificate: {e}")

    def get_public_service_ip(self, service_name: list[str]) -> dict:
        """
        Retrieves the public external IP for a Kubernetes LoadBalancer service.

        Args:
            service_name: The name of the Kubernetes service.

        Returns:
            The external IP address as a string, or an empty string if not found.
        """
        ips = {}
        try:
            for sn in service_name:
                cmd = ['kubectl', 'get', 'service', sn, '-o=jsonpath={.status.loadBalancer.ingress[0].ip}']
                result = exec_cmd(cmd)
                if result is not None:
                    public_ip = result
                    ips[sn] = public_ip
            print(f"All public ips extracted: {ips}")
        except subprocess.CalledProcessError as e:
            print(f"Error getting public IP for service '{service_name}': {e.stderr}")
        except Exception as e:
            print(f"An error occurred get_public_service_ip: {e}")
        return ips

    def create_secrets(self, env_cfg: dict):
        """
        Creates a new secret for each pod
        Acts as a env store
        """
        for env_id, struct in env_cfg.items():
            #get env args
            env_vars = struct["env"]

            # create deployment space
            struct["deployment"] = {}
            secret_name = env_id.replace("_", "-")
            struct["deployment"]["secret_name"] = secret_name

            cmd = [
                'kubectl',
                'create',
                'secret',
                'generic',
                secret_name
            ]

            for key, value in env_vars.items():
                cmd.append(f'--from-literal={key}={value}')

            print(f"Erstelle Secret: {secret_name}")
            exec_cmd(cmd)
            print(f"Secret '{secret_name}' successfully created")
        print("All secrets created")
        return env_cfg









    def get_intern_pod_ips(self, pod_names: list) -> dict:
        """
        Retrieves the internal IP and port for a list of pods.

        Args:
            pod_names: A list of pod names to query.

        Returns:
            A dictionary with the format {pod_name: "ip:port"}.
        """
        pod_ips = {}
        for pod_name in pod_names:
            try:
                # Use kubectl to get the pod's IP address using jsonpath
                cmd = ['kubectl', 'get', 'pod', pod_name, '-o=jsonpath={.status.podIP}']
                result = exec_cmd(cmd)
                if result is not None:

                    ip_address = result

                    # Check if an IP was found and add it to the dictionary
                    if ip_address:
                        pod_ips[pod_name] = f"{ip_address}:{self.container_port}"
                    else:
                        print(f"Warning: No IP found for pod '{pod_name}'.")
            except subprocess.CalledProcessError as e:
                print(f"Error getting IP for pod '{pod_name}': {e.stderr}")
            except Exception as e:
                print(f"An unexpected error occurred: {e}")

        print("Successfully retrieved pod IPs.")
        return pod_ips

    def create_or_update_deployment(self, env_id: str):
        image = self.artifact_admin.get_latest_image()
        print(f"Using image: {image}")
        cmd = [
            "kubectl", "create", "deployment", env_id, "--image", image, "--dry-run=client", "-o", "yaml"
        ]
        # apply damit es immer funktioniert (egal ob neu oder update)
        p1 = exec_cmd(cmd)
        if p1 is not None:
            cmd = ["kubectl", "apply", "-f", "-"]
            exec_cmd(cmd, inp=p1)
            print("Depl. proc finsied")






    def build_image(self, args: list[str]):
        """Run a command (list args) and stream output live."""
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            shell=os.name == "nt",
        )
        for line in process.stdout:
            print(line, end="")

        process.wait()
        if process.returncode != 0:
            raise RuntimeError(f"Command failed with code {process.returncode}")
        return process.returncode

    def create_app_process(self, app_name="app_name"):
        needed = {
            "Service": self.create_service_cfg,
            "Deployment": self.create_deployment_cfg,
            "Ingress": self.create_ingress_service_rule,
        }

        for resource, creator in needed.items():
            path = os.path.join(self.file_store.name, f"{resource}_{app_name}.yaml")
            content = creator()
            write_yaml(
                content=content,
                dest=path
            )

        status = self.check_ingress_controller()

        # INGRESS CONTROLLER
        if not status["installed"]:
            self.create_ingress_controller()

        for file in os.listdir(self.file_store.name):
            path = os.path.join(self.file_store.name, file)
            self.create_resource_from_yaml(
                file_path=path
            )
        print("Service created")

