import dotenv
from kubernetes import client
from kubernetes import config

dotenv.load_dotenv()

try:
    print("load_incluster_config")
    config.load_incluster_config()
except config.ConfigException as e:
    print(f"ConfigException: {e}")
    config.load_kube_config()
    print("kube_config load")
except Exception as e:
    print(f"Unknown err loading Kub cfg: {e}")
KUB_CLIENT = client.CoreV1Api()

init_in_local_project = f"""
gke-gcloud-auth-plugin --version
"""

INSTALL_AUTH_PLUGIN="""
gcloud
components
install
gke - gcloud - auth - plugin"""


CREATE_PRIVATE_KEY = None

def get_priv_key(PRIVATE_KEY_FILE):
    return f"""
PRIVATE_KEY_FILE="/tmp/ec_private.pem"
openssl ecparam -genkey -name prime256v1 -noout -out ${PRIVATE_KEY_FILE}
"""


def cget_creds():
    return f"""
    gcloud container clusters get-credentials autopilot-cluster-1 --region us-central1 --project aixr-401704
    """