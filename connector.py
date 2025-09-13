import os
import time

from fb_core.real_time_database import FirebaseRTDBManager
from gke_admin.build_admin import GKEAdmin
from utils.dj_websocket.handler import ConnectionManager
from utils.utils import Utils

class Connector:
    """
    Connects to spec. services in cluster
    """

    def __init__(
            self,
            pod_names,
            user_id,
            #cluster_root,
            gcp_project_id,
            cluster_domain,
            cluster_name,
            cluster_port,
            sub_domain
    ):
        self.ready_sessions = []
        self.all_authenticated = []

        self.user_id = user_id
        self.pod_names:list = pod_names

        #self.cluster_root = cluster_root
        self.instance = os.environ.get("FIREBASE_RTDB")


        self.project_id = gcp_project_id

        self.sub_domain = sub_domain
        self.domain = cluster_domain
        self.url = f"https://{self.sub_domain}.{self.domain}"
        self.cluster_subdomain = cluster_name
        self.cluster_port = int(cluster_port)

        self.utils = Utils()
        self.connection_manager = ConnectionManager()

        self.gke_admin = GKEAdmin(
            gcp_project_id=os.environ["GCP_PROJECT_ID"],
            cluster_domain=os.environ["CLUSTER_DOMAIN"],
            cluster_name=os.environ["GKE_SIM_CLUSTER_NAME"],
            cluster_port=os.environ["CLUSTER_PORT"],
            cluster_subdomain=os.environ["CLUSTER_SUB_DOMAIN"],
        )

        self.db_manager = FirebaseRTDBManager()

    async def connect_all_pods_process(self) -> list:
        print("Connection request process started")
        index = 0
        try:
            while len(self.all_authenticated) < len(self.pod_names):
                if index < 30:
                    for pod_name in self.pod_names:
                        success: bool = await self.connect_to_pod(
                            pod_name
                        )
                        if success is True:
                            self.all_authenticated.append(
                                pod_name
                            )
                        # Small delay between iters
                        time.sleep(5)
                        index += 1
                        print(f"{len(self.all_authenticated)}/{len(self.pod_names)} pods connected")
                else:
                    print("Max request attampts reached. Break process")
                    # Create List of missing pods that couldnt be connected to
                    self.pod_names = [name for name in self.pod_names if name not in self.all_authenticated]

            # return empty list if while loop finished
            return self.pod_names

        except Exception as e:
            print(f"Error: {e}")
        print("Finished Connection request process")


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
        #env-rajtigesomnlhfyqzbvx-yfbysoypkkxtxqeljjdj-58bf644885-ffb76
        try:
            cr = await self.utils.apost(
                url=f"{self.url}/{pod_name}",
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



"""

    def start_connection_thread(self):
        # FB Upsert thread
        print("Create Con thread")

        def _connect():
            missing_pods: list = asyncio.run(
                self.connect_all_pods_process()
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


"""
