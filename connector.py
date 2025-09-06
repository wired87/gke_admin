import asyncio
import os
import threading
import time

from fb_core.real_time_database import FirebaseRTDBManager
from gke_admin.build_admin import GKEAdmin
from utils.dj_websocket.handler import ConnectionManager
from utils.utils import Utils


class Connector:
    """
    Connects to spec. services in cluster
    """

    def __init__(self, env_cfg, user_id, cluster_root):
        self.ready_sessions = []

        self.env_cfg = env_cfg
        self.user_id = user_id

        self.cluster_root = cluster_root

        self.instance = os.environ.get("FIREBASE_RTDB")

        self.utils = Utils()
        self.connection_manager = ConnectionManager()
        self.gke_admin = GKEAdmin(
            user_id=user_id,
            gcp_project_id=os.environ["GCP_PROJECT_ID"],
            cluster_domain=os.environ["CLUSTER_DOMAIN"],
            cluster_name=os.environ["GKE_SIM_CLUSTER_NAME"],
            cluster_port=os.environ["CLUSTER_PORT"],
        )
        self.db_manager = FirebaseRTDBManager(
            database_url=self.instance,
        )

    async def connect_to_pods(self):
        """
        Monitor state till ready
        Connect to all pods
        save / return ips to connect to
        send auth payload
        """

        print("Establish connecgion to pods")

        all_pods = list(
            env_id.replace("_", "-")
            for env_id in self.env_cfg.keys()
        )

        self.start_connection_thread(
            pod_names=all_pods
        )
        print("All connections threads started")

        """
        self.ready_thread = threading.Thread(
            target=_connect,
            name="GLOBAL_READY_THREAD",
            daemon=True
        )
        """

        # Start Thread
        self.ready_thread.start()
        print("Threadstarted succesfuully")

    async def connect_all_pods_process(
            self,
            pod_names: list[str]
    ) -> list:
        print("Connection request process started")
        all_authenticated = []
        index = 0
        try:
            while len(all_authenticated) < len(pod_names):
                if index < 30:
                    for pod_name in pod_names:
                        success: bool = await self.connect_to_pod(
                            pod_name
                        )
                        if success is True:
                            all_authenticated.append(
                                all_authenticated
                            )
                        # Small delay between iters
                        time.sleep(1)
                        index += 1
                        print(f"{len(all_authenticated)}/{len(pod_names)} pods connected")
                else:
                    print("Max request attampts reached. Break process")
                    # Create List of missing pods that couldnt be connected to
                    missing_pods = [name for name in pod_names if name not in all_authenticated]
                    return missing_pods

            # return empty list if while loop finished
            return []

        except Exception as e:
            print(f"Error: {e}")
        print("Finished Connection request process")

    def start_connection_thread(self, pod_names):
        # FB Upsert thread
        print("Create Con thread")

        def _connect():
            missing_pods: list = asyncio.run(
                self.connect_all_pods_process(pod_names)
            )
            if len(missing_pods):
                # todo error intervention
                pass
            else:
                pass

        self.con_thread = threading.Thread(
            target=_connect,
            name="POD_INIT_CONNECTION",
            daemon=True  # Optional: Der Thread wird beendet, wenn das Hauptprogramm endet
        )

        # Start Thread
        self.con_thread.start()
        print("Connect to Pods thread started")

    async def connect_to_pod(self, pod_name):
        """
        Connect to a GKE cluster based on its ip:port
        :param ip:
        :param pod_name:
        :return:
        """

        auth_payload = {
            "type": "auth",
            "data": {
                "key": pod_name
            }
        }

        try:
            endpoint = f"{self.dom}"
            cr = await self.utils.apost(
                url=self.endpoint,
                data=auth_payload,
            )
            if cr and "response_key" in cr and "key" in cr and "session_id" in cr:
                if cr["key"] == pod_name:
                    # Successful pod authenticated -> append valid
                    print(f"Pod {pod_name} connected successfully")
                    return True
                else:
                    print(f"Invlalid key received: {cr['key']}")
            else:
                raise ValueError("No con request triger controlled Exceptio")
        except Exception as e:
            print(f"Error fetching: {e}")
        return False
