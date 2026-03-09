"""
gke_admin: deploy Docker images to a Kubernetes cluster (GKE or local).

Config from project root .env:
- GKE_CLUSTER_NAME, GCP_PROJECT_ID, GCP_REGION (or GKE_REGION) for GKE.
- LOCAL=true (or DEPLOY_LOCAL=true) to use local cluster (current kubectl context, e.g. kind/minikube).
"""
from _admin.gke_admin.deployer import GkeDeployer

__all__ = ["GkeDeployer"]
