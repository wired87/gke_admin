import os
import time

from fb_core.real_time_database import FirebaseRTDBManager
from gke_admin.core.build_admin import GKEBuildAdmin
from utils.dj_websocket.handler import ConnectionManager
from utils.utils import Utils

class Connector:
    """
    Connects to spec. services in cluster
    """

    def __init__(
            self,
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


        self.db_manager = FirebaseRTDBManager()

    async def connect_all_pods_process(
            self,
            pod_names
    ) -> list:
        print("Connection request process started")
        index = 0
        max_con_attempts=50
        try:
            while len(self.all_authenticated) < len(pod_names):
                if index < max_con_attempts:
                    print("connection index", index)
                    for pod_name in pod_names:
                        success: bool = await self.connect_to_pod(
                            pod_name
                        )
                        print(f"{pod_name} connection success: {success}")
                        if success is True:
                            self.all_authenticated.append(
                                pod_name
                            )

                        # Small delay between iters
                        time.sleep(5)
                        index += 1
                        print(f"{len(self.all_authenticated)}/{len(pod_names)} pods connected")
                else:
                    print("Max request attampts reached. Break process")
                    # Create List of missing pods that couldnt be connected to
                    pod_names = [name for name in pod_names if name not in self.all_authenticated]
                    break
            # return empty list if while loop finished
            return pod_names

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
            response = await self.utils.apost(
                url=f"{self.url}/{pod_name}",
                data=auth_payload,
            )
            if response and "response_key" in response and "key" in response and "session_id" in response:
                if response["key"] == pod_name:
                    # Successful pod authenticated -> append valid
                    print(f"Pod {pod_name} connected successfully")
                    return True
                else:
                    print(f"Invlalid key received: {response['key']}")
            else:
                raise ValueError(f"Invalid response payload: {response}")
        except Exception as e:
            print(f"Error fetching: {e}")
        return False

