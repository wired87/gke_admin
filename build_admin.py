import os
import pprint
import subprocess
import time
from tempfile import TemporaryDirectory

from kubernetes import client, config

from artifact_registry.artifact_admin import ArtifactAdmin
from gke_admin.cluster_admin import ClusterManager
from gke_admin.ingress.ControllerManager import IngressControllerManager
from gke_admin.ip_creator import IPManager
from utils.file._yaml import write_yaml
from utils.run_subprocess import exec_cmd

import dotenv
dotenv.load_dotenv()

class GKEAdmin(
    ClusterManager,
    IPManager
):
    def __init__(
            self, 
            gcp_project_id, 
            cluster_domain, 
            cluster_name, 
            cluster_port, 
            cluster_subdomain,
            app_name=None, 
            repo="qfs-repo", 
            image="qfs", 
            cfg=None, 
    ):

        self.region = 'us-central1'
        self.cluster_name = cluster_name

        # AUTH
        self.authenticate_cluster()
        config.load_kube_config()

        # CLIENTS
        self.client = client.ApiClient()
        self.core = client.CoreV1Api(self.client)


        # PARENTS
        ClusterManager.__init__(self, cluster_name, self.region, gcp_project_id)

        # CLASSES
        self.ip_manager = IPManager(
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

        # IMAGE COMPONENTS
        self.app_name = app_name
        self.cfg = cfg

        self.repo = repo

        self.cluster_manager = ClusterManager(
            cluster_name=cluster_name,
            region=self.region,
            project_id=gcp_project_id
        )

        # Check create cluster
        self.cluster_manager()

        self.project_id = gcp_project_id
        self.domain = cluster_domain
        self.cluster_subdomain = cluster_subdomain
        self.cluster_port = int(cluster_port)

        self.artifact_admin = ArtifactAdmin()
        self.file_store = TemporaryDirectory()

        # RAY cluster image
        self.image = image
        self.tag = "latest"

        self.full_tag = None

    ################################### YAML

    def create_resource_from_yaml(self, file_path: str):
        """
        Creates a Kubernetes Pod from a given YAML file.
        """

        cmd = ['kubectl', 'apply', '-f', file_path]
        result = exec_cmd(cmd)

        if result is not None:
            print(f"Resource was successfully created from '{file_path}'.")
        else:
            raise ValueError("Failed create_resource_from_yaml")


    def create_deployment_cfg(
            self,
            app_name=None,
            cfg_struct=None
    ):
        try:
            if app_name is None:
                app_name = self.app_name

            print("cfg struct create_deployment_cfg")
            pprint.pp(cfg_struct)

            creator_struct = {
                **self.create_pod_metadata(name=app_name),
                "spec": self.get_spec(app_name, world_cfg_item=cfg_struct)
            }

            return creator_struct
        except Exception as e:
            print(f"Error creacreate_deployment_cfgte_service_cfg: {e}")





    def get_spec(
            self,
            env_id,
            world_cfg_item=None
    ):
        if world_cfg_item is None:
            world_cfg_item = self.cfg

        if env_id is None:
            env_id = self.app_name

        container_spec = self.containers_section(env_id, world_cfg_item)
        print("cfg struct get_spec")
        pprint.pp(world_cfg_item)

        spec_struct = {
            "replicas": 1,
            "selector": {
                "matchLabels": {
                    "app": env_id
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": env_id
                    },

                },
                "spec": {
                    "containers": container_spec,
                }
            },
        }

        return spec_struct


    def create_pod_metadata(
            self,
            name: str,
            labels: dict = {},
            resource_kind="Deployment",
            annotations={}
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
            "apiVersion": "apps/v1",
            "kind": resource_kind,
            "metadata": {
                "name": name.replace("_", "-"),
                "labels": labels,
                "annotations": annotations
            }
        }

    def containers_section(
            self,
            name,
            world_cfg_item,
            image=None
    ) -> list:
        print("Set container section")
        #if image is None:
        #if self.image is None:
        image = self.artifact_admin.get_latest_image()
        """
        else:
            image = self.image
        """
        if name is None:
            name = self.app_name

        resources = self.create_resources_spec(
            world_cfg_item
        )

        container_struct = [
            {
                "name": name.replace("_", "-"),
                "image": image,
                "ports": [
                    {
                        "containerPort": self.cluster_port,
                        "protocol": "TCP"
                    }
                ],
                "env": world_cfg_item["env"],
                "resources": resources
            }
        ]
        return container_struct



    def create_ingress_service_rule(
            self,
            app_name=None
    ):
        if app_name is None:
            app_name = self.app_name
        app_name=app_name.replace('_', '-')

        annotations = {
            "nginx.ingress.kubernetes.io/rewrite-target": "/",
            "nginx.ingress.kubernetes.io/proxy-body-size": "50m",
            "nginx.ingress.kubernetes.io/proxy-connect-timeout": "3000",
            "nginx.ingress.kubernetes.io/proxy-read-timeout": "3000",
            "nginx.ingress.kubernetes.io/proxy-send-timeout": "3000",
            "nginx.ingress.kubernetes.io/send-timeout": "3000",
            "nginx.ingress.kubernetes.io/ssl-redirect": "true",
        }

        ingress_controller = {
            **self.create_pod_metadata(
                name=f"ingress-{app_name}",
                labels={},
                resource_kind="Ingress",
                annotations={}
            ),
            "apiVersion": "networking.k8s.io/v1",
            "kind": "Ingress",
            "metadata": {
                "name": f"{self.domain}-ingress",
                "annotations": annotations
            },
            "spec": {
                "tls": [
                    {
                        "hosts": [
                            f"{self.cluster_subdomain}.{self.domain}",
                            f"www.{self.cluster_subdomain}.{self.domain}"
                        ],
                        #"secretName": f"{self.domain}-tls"  # muss als Secret vorhanden sein
                    }
                ],
                "rules": [
                    self.create_ingress_rule(
                        path=f"/{app_name}",
                        name=app_name,
                    ),
                ]
            }
        }
        print("Ingress rule spec created")
        return ingress_controller

    def get_nginx_controller(self):
        cmd = [
            "kubectl", "get", "ingress", "--all-namespaces", "-o",
            "jsonpath={range .items[*]}{.metadata.namespace}:{.metadata.name}{\"\\n\"}{end}"
        ]
        result = exec_cmd(cmd)
        return result


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
                "host": f"{self.cluster_subdomain}.{self.domain}",
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




    def create_resources_spec(self, world_cfg):
        """
        Erstellt das Python-Wörterbuch für die Ressourcen-Definition
        eines Containers in einem Kubernetes-Manifest.
        """
        return {
            "requests": {
                "cpu": world_cfg["resources"]["cpu"],
                "memory": world_cfg["resources"]["mem"]
            },
            "limits": {
                "cpu": world_cfg["resources"]["cpu_limit"],
                "memory": world_cfg["resources"]["mem_limit"]
            }
        }

    def create_service_cfg(
            self,
            service_type="ClusterIP",  # "LoadBalancer",
            namespace="default",
            api_version="v1",
            kind="Service",
            name=None
    ):
        try:
            if name is None:
                name = self.app_name
            return {
                "apiVersion": api_version,
                "kind": kind,
                "metadata": {
                    "name": name,
                    "namespace": namespace,
                },
                "spec": {
                    "selector": {
                        "app": name
                    },
                    "ports": [
                        {
                            "port": self.cluster_port,
                            "targetPort": self.cluster_port
                        }
                    ],
                    "type": service_type,
                }
            }
        except Exception as e:
            print(f"Error create_service_cfg: {e}")

    ########### CMD ##########################

    def get_pod_info(self, pod_name, namespace):
        try:
            pod_details = self.core.read_namespaced_pod(
                name=pod_name,
                namespace=namespace,
            )
            print("Pod details successfully retrieved:")
            print(pod_details.to_dict())
            return pod_details.to_dict()
        except client.ApiException as e:
            print(f"Error retrieving pod details: {e}")


    def await_pod_state(self, env_ids:list):
        """
        Waits in a loop until all pods in a given namespace are in the 'Running' state.

        Args:
            v1_api: An instance of the Kubernetes CoreV1Api.
            namespace (str): The namespace to check for pods. Defaults to "default".

        Returns:
            bool: True when all pods are running.
        """
        print(f"Waiting for pods {env_ids} to be 'Running'...")
        active = []
        converted_env_ids = [
            env_id.replace("_", "-")
            for env_id in env_ids
        ]

        pod_list = self.core.list_pod_for_all_namespaces()

        i = 0
        while len(converted_env_ids) > len(active):
            try:
                print(f"Check iter: {i}")
                # List all pods in the specified namespace

                # Check the status of each pod
                for pod in pod_list.items:
                    name = pod.metadata.name

                    for env_id in converted_env_ids:
                        if name == env_id or name.startswith(env_id) or env_id in name:
                            status = pod.status.phase
                            print("Pod State:", status)
                            #namespace = pod.metadata.namespace
                            if status == "Running":
                                active.append(name)
                                print(f"Pod '{name}' is in state '{status}'.")
                                print(f"{len(active)}/{len(converted_env_ids)} creaed pods are active")

                # Wait for a few seconds before checking again
                time.sleep(2)
            except client.ApiException as e:
                print(f"Error checking pod status: {e}")
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
        print("All created pods are Running")
        return active








    def build_secrets(self, env_dict: dict) -> list:
        # SET SECRETS
        secrets = ["--update-secrets"]
        for key, val in env_dict.items():
            secrets.append(f"{key}={val},")
        return secrets


    def create_deployments_process(self, env_cfg:dict) -> dict:
        print(f"create_deployments_process env_cfg: {env_cfg}")

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
            pprint.pp(env_cfg)

        except Exception as e:
            print(f"Exception while create_deployments_process: {e}")

        finally:
            print("GKE create_deployments_process process finalized.")

        return env_cfg

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

    def authenticate_cluster(self):
        auth_command = f"gcloud container clusters get-credentials {self.cluster_name} --region us-central1 --project aixr-401704"
        exec_cmd(auth_command)


        print("Authenticated")


    def get_pod_names(self, world_cfgs):
        pod_identifiers = {}
        for env_id, creation_cmd in world_cfgs.items():
            all_pods = self.get_pods()
            if all_pods is not None:
                for pod in list(all_pods):
                    if pod.startswith(pod) and env_id not in pod_identifiers:
                        world_cfgs[env_id]["pod_name"] = pod
        print(f"envcfg updated with pod names: {world_cfgs}")
        return world_cfgs



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
        services = self.v1.list_namespaced_service(
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
        pprint.pp(result)
        return result

    def get_depl_cmd(self, env_cfg:dict):
        try:
            for env_id, struct in env_cfg.items():
                print(F"Create depl cmd rom struct:")
                pprint.pp(struct)

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


    def cleanup(self):
        self.delete_all_deployments()
        self.delete_all_services()
        self.delelte_pods()

    def delelte_pods(self, pod_names:list[str]=None, all=False):
        # Löschbefehl für den Pod
        if all is True:
            pod_names = self.get_pods()

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



    def get_pods(self) -> list:
        # Pods anzeigen
        print("Zeige erstellte Pods an...")
        cmd = ['kubectl', 'get', 'pods']
        result = exec_cmd(cmd)
        print("Alle Pods angezeigt.")
        if result is not None:
            pod_lines = result.split('\n')
            pod_names = [line.split()[0] for line in pod_lines if line]
            return pod_names


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

if __name__ == "__main__":
    admin = GKEAdmin(
        gcp_project_id=os.environ["GCP_PROJECT_ID"],
        cluster_domain=os.environ["CLUSTER_DOMAIN"],
        cluster_name=os.environ["GKE_SIM_CLUSTER_NAME"],
        cluster_port=os.environ["CLUSTER_PORT"],
        cluster_subdomain=os.environ["CLUSTER_SUB_DOMAIN"],
    )
    #admin.delelte_pods(all=True)
    admin.cleanup()
"""

# Services im ingress-nginx Namespace
cmd_svc = ["kubectl", "get", "svc", "-n", "ingress-nginx", "-o", "jsonpath={.items[*].metadata.name}"]
svc_result = exec_cmd(cmd_svc)
if svc_result and svc_result:
    result["services"] = svc_result.split()

# Installiert, wenn Controller-Pod und Service existieren
if any("ingress-nginx-controller" in s for s in result["services"]):
    result["installed"] = True
            cmd_pods = ["kubectl", "get", "pods", "-n", "ingress-nginx", "-o", "jsonpath={.items[*].status.phase}"]
            pods_status = exec_cmd(cmd_pods)
            if pods_status and pods_status:
                result["pods"] = pods_status.split()
"""