import json
import os

from utils.run_subprocess import exec_cmd
import dotenv
dotenv.load_dotenv()

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
        self.check_cluster_exists(create=True)

    def await_cluster(self):
        # Wait for the cluster to be in the RUNNING state
        print("Aweait cluster readyness")
        wait_cmd = [
            "gcloud", "container", "clusters", "wait",
            self.cluster_name,
            "--region", self.region,
            "--for-status=RUNNING",
            "--project", self.project_id,
        ]
        exec_cmd(wait_cmd)
        print(f"GKE cluster '{self.cluster_name}' is now ready.")


    def list_all_clusters(self):
        """List all clusters in all regions for a project."""
        cmd = [
            "gcloud", "container", "clusters", "list",
            "--project", self.project_id,
            "--format", "json"
        ]
        output = exec_cmd(cmd)
        clusters = json.loads(output)
        return clusters


    def delete_cluster_list(self):
        clusters = self.list_all_clusters()
        if not clusters:
            print("No clusters found.")
            return
        for c in clusters:
            cluster_name = c["name"]
            location = c["location"]
            self.delete_cluster(cluster_name, location)


    def check_cluster_exists(self, create=True):
        # Check if the cluster exists
        check_cmd = [
            "gcloud",
            "container",
            "clusters",
            "list",
            "--project", self.project_id,
            "--filter", f"name={self.cluster_name}",
            "--format", "value(name)"
        ]
        existing_cluster = exec_cmd(check_cmd)
        print("Check for cluster finished")
        if existing_cluster:
            print(f"GKE cluster '{self.cluster_name}' already exists.")
            return
        if create is True:
            self.create_cluster()


    def create_cluster(self):
        # Define the command to create the cluster
        create_cmd = [
            "gcloud", "container",
            "clusters",
            "create-auto", self.cluster_name,
            "--project", self.project_id,
            "--region", self.region,
            "--release-channel=regular",
            "--quiet"
        ]
        # Execute the create command
        exec_cmd(create_cmd)
        self.await_cluster()

        print("Cluster creation finshed")




    def delete_cluster(self, cluster_name, location):
        """
        Deletes a Google Kubernetes Engine (GKE) cluster.

        Args:
            cluster_name (str): The name of the GKE cluster to delete.
            zone (str): The compute zone where the cluster is located.
        """
        if cluster_name is None:
            cluster_name = self.cluster_name
        if location is None:
            location = self.region
        command = [
            'gcloud', 'container', 'clusters', 'delete', cluster_name, f"--location={location}", "--quiet"
        ]
        print("Running cmd:", command)
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

"""
 "--num-nodes", "1",
            "--min-nodes", "1",
            "--max-nodes", "2",
            "--async",
            "--disk-size", "15",
            "--machine-type", "e2-standard-4",
"""