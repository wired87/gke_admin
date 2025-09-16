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
            cluster_port,
            request_type="https",
    ):
        self.ready_sessions = []
        self.all_authenticated = []
        self.request_type=request_type
        self.user_id = user_id

        self.instance = os.environ.get("FIREBASE_RTDB")

        self.project_id = gcp_project_id

        self.domain = cluster_domain
        self.url = f"{request_type}://{self.domain}"
        self.cluster_port = int(cluster_port)

        self.utils = Utils()
        self.connection_manager = ConnectionManager()
        self.db_manager = FirebaseRTDBManager()


    async def connect_all_pods_process(
            self, env_ids
    ) -> list:
        print("Connection request process started")
        index = 0

        env_ids = [
            env_id.replce("_", "-")
            for env_id in env_ids
        ]


        max_con_attempts=50
        try:
            while len(self.all_authenticated) < len(env_ids):
                if index < max_con_attempts:
                    print("connection index", index)
                    for env_id in env_ids:
                        success: bool = await self.connect_to_pod(
                            env_id
                        )
                        print(f"{env_id} connection success: {success}")
                        if success is True:
                            self.all_authenticated.append(
                                env_id
                            )

                        # Small delay between iters
                        time.sleep(5)
                        index += 1
                        print(f"{len(self.all_authenticated)}/{len(env_ids)} pods connected")
                else:
                    print("Max request attampts reached. Break process")
                    # Create List of missing pods that couldnt be connected to
                    pod_names = [name for name in env_ids if name not in self.all_authenticated]
                    break
            # return empty list if while loop finished
            return env_ids

        except Exception as e:
            print(f"Error: {e}")
        print("Finished Connection request process")


    async def connect_to_pod(self, env_id):
        """
        Connect to a GKE cluster based on its ip:port
        :param ip:
        :param pod_name:
        :return:
        """

        auth_payload = {
            "type": "auth",
            "data": {
                "key": env_id
            }
        }

        url = f"{self.url}/{env_id}/root/"
        print("Requestig:", url)

        #env-rajtigesomnlhfyqzbvx-yfbysoypkkxtxqeljjdj-58bf644885-ffb76
        try:
            response = await self.utils.apost(
                url=url,
                data=auth_payload,
            )
            if response and "response_key" in response and "key" in response and "session_id" in response:
                if response["key"] == env_id:
                    # Successful pod authenticated -> append valid
                    print(f"Pod {env_id} connected successfully")
                    return True
                else:
                    print(f"Invlalid key received: {response['key']}")
            else:
                raise ValueError(f"Invalid response payload: {response}")
        except Exception as e:
            print(f"Error fetching: {e}")
        return False

