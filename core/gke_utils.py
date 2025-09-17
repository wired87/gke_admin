import os
import time

from utils.file._yaml import write_yaml
from utils.run_subprocess import exec_cmd

class GKEUtils:

    def __init__(
            self,
            client,
            core,
            app_name,
            cluster_port,
            cluster_subdomain,
            cluster_domain,
            artifact_admin,
            secret_name,
    ):
        self.client = client
        self.core = core
        self.app_name = app_name
        self.cluster_port = cluster_port
        self.cluster_subdomain = cluster_subdomain
        self.cluster_domain = cluster_domain
        self.artifact_admin=artifact_admin
        self.secret_name=secret_name



    def create_deployment_cfg(
            self,
            app_name=None,
            cfg_struct=None
    ):
        try:
            if app_name is None:
                app_name = self.app_name

            print("cfg struct create_deployment_cfg")
            #pprint.pp(cfg_struct)

            creator_struct = {
                **self.create_pod_metadata(name=app_name),
                "spec": self.get_spec(app_name, world_cfg_item=cfg_struct)
            }

            return creator_struct
        except Exception as e:
            print(f"Error creacreate_deployment_cfgte_service_cfg: {e}")

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







    def get_spec(
            self,
            app_name,
            world_cfg_item
    ):
        if app_name is None:
            app_name = self.app_name

        container_spec = self.containers_section(
            app_name,
            world_cfg_item
        )

        print("cfg struct get_spec")

        spec_struct = {
            "replicas": 1,
            "selector": {
                "matchLabels": {
                    "app": app_name
                }
            },
            "template": {
                "metadata": {
                    "labels": {
                        "app": app_name
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
            annotations={},
            api_version="apps/v1",
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
            "apiVersion": api_version,
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
        # if image is None:
        # if self.image is None:
        image = self.artifact_admin.get_latest_image()
        if image is None:
            raise ValueError(
                "Couldnt find an image in AR"
            )

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



    def create_resource_cfgs(self, deployment_struct):
        """
        Create an deployment and ingress rule cfg for all cfgs
        """
        print("===============RESOURCE CREATION=================")
        cfg_struct = {}
        try:
            for app_name, struct in deployment_struct.items():
                app_name = app_name.replace('_', '-')
                cfg_struct[app_name] = {}
                cfg_struct[app_name]["deployment"] = self.create_deployment_cfg(
                    app_name,
                    struct)

                cfg_struct[app_name]["ingress"] = self.create_ingress_service_rule(
                    app_name)

                cfg_struct[app_name]["service"] = self.create_service_cfg(
                    name=app_name,
                    service_type="ClusterIP"
                )

            print("Cfgs created and saved locally")
            return cfg_struct
        except Exception as e:
            print(f"Err create_resource_cfgs: {e}")

    def write_resource_cfgs_to_file_store(
            self,
            resource_cfg, # app_name: deployment:dict, ingress:dict
            file_store_name,
    ):
        path_struct = {}
        try:
            for app_name, struct in resource_cfg.items():
                resources = list(struct.keys())
                for rcs in resources:
                    # WRITE DEPLOYMENT
                    path = os.path.join(
                        file_store_name,
                        f"{rcs}__{app_name}.yaml"
                    )
                    write_yaml(
                        content=struct[rcs],
                        dest=path
                    )
                    path_struct[app_name][rcs] = path
                    print(f"{rcs} written")
            print("Entire content written to file store>")
            return path_struct
        except Exception as e:
            print(f"Err write_resource_cfgs_to_file_store: {e}")






    def create_ingress_service_rule(
            self,
            app_name=None,
            load_balancer_ip=None,

            secret_name=None
    ):
        if app_name is None:
            app_name = self.app_name

        if secret_name is None:
            secret_name = self.secret_name

        cert = f"{self.cluster_domain.replace('.','-')}"
        annotations = {
            "nginx.ingress.kubernetes.io/rewrite-target": "/",
            "nginx.ingress.kubernetes.io/proxy-body-size": "50m",
            "nginx.ingress.kubernetes.io/proxy-connect-timeout": "3000",
            "nginx.ingress.kubernetes.io/proxy-read-timeout": "3000",
            "nginx.ingress.kubernetes.io/proxy-send-timeout": "3000",
            "nginx.ingress.kubernetes.io/send-timeout": "3000",
            "nginx.ingress.kubernetes.io/ssl-redirect": "true",
        }

        try:
            ingress_controller = {
                **self.create_pod_metadata(
                    api_version="networking.k8s.io/v1",
                    name=f"ingress-{app_name}",
                    labels={},
                    resource_kind="Ingress",
                    annotations=annotations
                ),
                "spec": {
                    "ingressClassName": "nginx",
                    "tls": [
                        {
                            "hosts": [
                                f"{self.cluster_domain}",
                            ],
                            "secretName": secret_name

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
        except Exception as e:
            print(f"Err create_ingress_service_rule: {e}")




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
                "host": self.cluster_domain,
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

    def get_pod_list(self):
        pod_list = self.core.list_namespaced_pod(
            namespace="default"
        )
        print(f"received {len(pod_list.items)} pods:")
        """for pod in pod_list.items:
            name = pod.metadata.name
            print(name)
        """
        return pod_list





    def await_pod_state(self, env_ids:list):
        """
        Waits in a loop until all pods in a given namespace are in the 'Running' state.

        Args:
            v1_api: An instance of the Kubernetes CoreV1Api.
            namespace (str): The namespace to check for pods. Defaults to "default".

        Returns:
            bool: True when all pods are running.
        """
        print(f"========== AWAIT RUNNING POD STATE ==========")
        try:
            active_pods = []
            converted_env_ids = [
                env_id.replace("_", "-")
                for env_id in env_ids
            ]

            i = 0
            while len(converted_env_ids) > len(active_pods):
                try:
                    print(f"Check iter: {i}")

                    i+=1

                    # List all pods in the specified namespace
                    pod_list = self.get_pod_list()

                    # Check the status of each pod
                    for pod in pod_list.items:
                        name = pod.metadata.name
                        for env_id in converted_env_ids:
                            if name == env_id or name.startswith(env_id) or env_id in name:
                                status = pod.status.phase
                                print(f"{name} pod state:", status)
                                if status == "Running":
                                    active_pods.append(name)
                                    print(f"{len(active_pods)}/{len(converted_env_ids)} created pods are active")

                    # Wait for a few seconds before checking again
                    time.sleep(2)
                except Exception as e:
                    print(f"An unexpected error occurred: {e}")
            print("All created pods are Running")
            return active_pods

        except Exception as e:
            print(f"Err await_resources_alive: {e}")

    def create_resources_spec(self, world_cfg):
        """
        Erstellt das Python-Wörterbuch für die Ressourcen-Definition
        eines Containers in einem Kubernetes-Manifest.
        """
        return {
            "requests": {
                "cpu": world_cfg["cpu"],
                "memory": world_cfg["mem"]
            },
            "limits": {
                "cpu": world_cfg["cpu_limit"],
                "memory": world_cfg["mem_limit"]
            }
        }


    def check_service_exists(
            self,
            service_name,
            namespace="default",
    ):
        print(f"start check_service_exists {service_name} -n {namespace}")
        try:
            service = self.core.read_namespaced_service(
                name=service_name,
                namespace=namespace
            )
            print(f"Service found: {service}")
            if service is not None:
                service_dict = service.to_dict()
                return service_dict
        except Exception as e:
            print(f"Err check_service_exists: {e}")





    def create_service_cfg(
            self,
            service_type="LoadBalancer",  # "ClusterIP(Kein direkter Zugriff von außen.)",
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

