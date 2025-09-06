import os

from utils.run_subprocess import exec_cmd
import dotenv
dotenv.load_dotenv()
#gcloud container clusters create SIMS --project aixr-401704 --region us-central1 --enable-autoscaling --num-nodes 1 --min-nodes 1 --max-nodes 5 --async --machine-type e2-highcpu-4
class ClusterManager:
    """
    Manages the lifecycle of a GKE cluster.
    """

    def __init__(self, cluster_name: str, region: str, project_id: str):
        self.cluster_name = cluster_name
        self.region = region
        self.project_id = project_id

    def __call__(self):
        """
        Checks if a GKE cluster exists and creates it if it does not.
        Waits for the cluster to be ready after creation.
        """
        print(f"Checking for GKE cluster '{self.cluster_name}' in project '{self.project_id}'...")

        # Check if the cluster exists
        check_cmd = [
            "gcloud", "container", "clusters", "list",
            "--project", self.project_id,
            "--filter", f"name={self.cluster_name}",
            "--format", "value(name)"
        ]

        existing_cluster = exec_cmd(check_cmd)
        if existing_cluster:
            print(f"GKE cluster '{self.cluster_name}' already exists.")
            return

        # Define the command to create the cluster
        create_cmd = [
            "gcloud", "container", "clusters", "create", self.cluster_name,
            "--project", self.project_id,
            "--region", self.region,
            "--enable-autoscaling",
            "--num-nodes", "1",
            "--min-nodes", "1",
            "--max-nodes", "3",
            "--async",
            "--disk-size", "10",
            "--machine-type", "e2-standard-4",
        ]

        print(f"Creating GKE cluster '{self.cluster_name}'...")
        try:
            # Execute the create command
            exec_cmd(create_cmd)
            print("Cluster creation initiated. Waiting for the cluster to be ready...")

            # Wait for the cluster to be in the RUNNING state
            wait_cmd = [
                "gcloud", "container", "clusters", "wait",
                self.cluster_name,
                "--region", self.region,
                "--for-status=RUNNING",
                "--project", self.project_id,
            ]
            exec_cmd(wait_cmd)
            print(f"GKE cluster '{self.cluster_name}' is now ready.")
        except Exception as e:
            print(f"Failed to create or wait for cluster: {e}")
            raise

    def delete_gke_cluster(self):
        """
        Deletes a Google Kubernetes Engine (GKE) cluster.

        Args:
            cluster_name (str): The name of the GKE cluster to delete.
            zone (str): The compute zone where the cluster is located.
        """
        command = [
            'gcloud', 'container', 'clusters', 'delete', "autopilot-cluster-1",
            '--zone', self.region,
        ]
        exec_cmd(command)

if __name__ == "__main__":
    # Example usage: Replace these with your actual cluster details
    # For demonstration, we use environment variables.
    CLUSTER_NAME = os.environ.get("GKE_SIM_CLUSTER_NAME")
    REGION = os.environ.get("GCP_REGION", "us-central1")
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "your-gcp-project-id")
    print("CLUSTER_NAME", CLUSTER_NAME)
    print("REGION", REGION)
    print("PROJECT_ID", PROJECT_ID)
    try:
        cluster_manager = ClusterManager(
            cluster_name=CLUSTER_NAME,
            region=REGION,
            project_id=PROJECT_ID
        )
        cluster_manager.delete_gke_cluster()
    except Exception as e:
        print(f"An error occurred: {e}")
