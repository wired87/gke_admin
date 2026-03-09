"""
Deploy built images to a Kubernetes cluster (GKE or local).
Reads cluster config from .env at project root; LOCAL=true uses local cluster.
"""
import os
import subprocess
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


def _project_root() -> Path:
    """Project root (parent of _admin)."""
    return Path(__file__).resolve().parent.parent.parent


def _load_env() -> None:
    root = _project_root()
    env_path = root / ".env"
    if load_dotenv and env_path.exists():
        load_dotenv(env_path)


def _is_local() -> bool:
    """True if deploy target is local cluster (from .env LOCAL or DEPLOY_LOCAL)."""
    _load_env()
    v = (
        os.environ.get("LOCAL", "").strip().lower()
        or os.environ.get("DEPLOY_LOCAL", "").strip().lower()
    )
    return v in ("true", "1", "yes")


class GkeDeployer:
    """
    Deploy one or more Docker images to a Kubernetes cluster.
    - If LOCAL (or DEPLOY_LOCAL) is set in .env: use current kubectl context (local cluster).
    - Else: use GKE cluster from .env (GKE_CLUSTER_NAME, GCP_PROJECT_ID, GCP_REGION/GKE_REGION).
    """

    def __init__(
        self,
        cluster_name: str | None = None,
        project_id: str | None = None,
        region: str | None = None,
        local: bool | None = None,
    ):
        _load_env()
        self.local = local if local is not None else _is_local()
        self.cluster_name = cluster_name or os.environ.get("GKE_CLUSTER_NAME", "")
        self.project_id = project_id or os.environ.get("GCP_PROJECT_ID", "")
        self.region = region or os.environ.get("GKE_REGION") or os.environ.get("GCP_REGION", "")

    def log_cloud_env(self) -> None:
        """Collect and log env vars used for cloud (GKE) deploy. Call when LOCAL is not set."""
        if self.local:
            return
        env_vars = {
            "GKE_CLUSTER_NAME": self.cluster_name or os.environ.get("GKE_CLUSTER_NAME", ""),
            "GCP_PROJECT_ID": self.project_id or os.environ.get("GCP_PROJECT_ID", ""),
            "GCP_REGION": self.region or os.environ.get("GKE_REGION") or os.environ.get("GCP_REGION", ""),
            "GCP_ARTIFACT_REPO": os.environ.get("GCP_ARTIFACT_REPO", "qfs-repo"),
        }
        print("[gke_admin] Deploying to cloud (GKE). Env vars:", env_vars)

    def ensure_context(self) -> bool:
        """
        Ensure kubectl context is set: for GKE, run gcloud container clusters get-credentials.
        For local, assume context is already set (e.g. kind, minikube).
        Returns True if context is ready.
        """
        if self.local:
            try:
                out = subprocess.run(
                    ["kubectl", "config", "current-context"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                print(f"[gke_admin] Using local context: {out.stdout.strip()}")
                return True
            except (subprocess.CalledProcessError, FileNotFoundError) as e:
                print(f"[gke_admin] Local kubectl context not ready: {e}")
                return False

        if not all([self.cluster_name, self.project_id, self.region]):
            print(
                "[gke_admin] GKE config missing. Set GKE_CLUSTER_NAME, GCP_PROJECT_ID, "
                "GCP_REGION (or GKE_REGION) in .env, or use LOCAL=true for local cluster."
            )
            return False

        try:
            subprocess.run(
                [
                    "gcloud",
                    "container",
                    "clusters",
                    "get-credentials",
                    self.cluster_name,
                    "--region",
                    self.region,
                    "--project",
                    self.project_id,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"[gke_admin] GKE context set: {self.cluster_name} ({self.region})")
            return True
        except subprocess.CalledProcessError as e:
            print(f"[gke_admin] Failed to get GKE credentials: {e.stderr}")
            return False
        except FileNotFoundError:
            print("[gke_admin] gcloud not found. Install Google Cloud SDK.")
            return False

    def deploy_image(
        self,
        image_name: str,
        image_tag: str = "latest",
        deployment_name: str | None = None,
        namespace: str = "default",
    ) -> bool:
        """
        Deploy a single image as a Kubernetes Deployment (simple 1-replica).
        deployment_name defaults to image name (before colon) with invalid chars replaced.
        """
        if not self.ensure_context():
            return False

        name = deployment_name or image_name.split(":")[0].split("/")[-1].replace(".", "-").replace("_", "-")
        if ":" in image_name:
            image = image_name
        else:
            image = f"{image_name}:{image_tag or 'latest'}"

        # Minimal deployment manifest
        manifest = f"""
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {name}
  namespace: {namespace}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: {name}
  template:
    metadata:
      labels:
        app: {name}
    spec:
      containers:
      - name: {name}
        image: {image}
        imagePullPolicy: Always
---
apiVersion: v1
kind: Service
metadata:
  name: {name}
  namespace: {namespace}
spec:
  selector:
    app: {name}
  ports:
  - port: 8080
    targetPort: 8080
  type: ClusterIP
"""
        try:
            proc = subprocess.run(
                ["kubectl", "apply", "-f", "-"],
                input=manifest.strip(),
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"[gke_admin] Deployed {name} -> {image}")
            if proc.stdout:
                print(proc.stdout.strip())
            return True
        except subprocess.CalledProcessError as e:
            print(f"[gke_admin] Deploy failed for {name}: {e.stderr}")
            return False

    def deploy_image_by_uri(
        self,
        image_uri: str,
        deployment_name: str | None = None,
        namespace: str = "default",
    ) -> bool:
        """Deploy using full image URI (e.g. registry/project/repo/name:tag)."""
        # name from last path segment before : or /
        name = image_uri.split("/")[-1].split(":")[0].replace(".", "-").replace("_", "-")
        return self.deploy_image(
            image_name=image_uri,
            image_tag="",
            deployment_name=deployment_name or name,
            namespace=namespace,
        )

    def deploy_all(
        self,
        image_names: list[str],
        tag: str = "latest",
        namespace: str = "default",
    ) -> list[tuple[str, bool]]:
        """Deploy each local image name; returns list of (image_name, success)."""
        if not image_names:
            return []
        if not self.ensure_context():
            print("[gke_admin] Cluster context not ready; skipping all deploys.")
            return [(img, False) for img in image_names]
        results = []
        for img in image_names:
            ok = self.deploy_image(img, image_tag=tag, namespace=namespace)
            results.append((img, ok))
        return results

    def deploy_all_by_uri(
        self,
        image_uris: list[str],
        namespace: str = "default",
    ) -> list[tuple[str, bool]]:
        """Deploy each full image URI (after push to registry). Returns list of (uri, success)."""
        if not image_uris:
            return []
        if not self.ensure_context():
            print("[gke_admin] Cluster context not ready; skipping all deploys.")
            return [(uri, False) for uri in image_uris]
        results = []
        for uri in image_uris:
            ok = self.deploy_image_by_uri(uri, namespace=namespace)
            results.append((uri, ok))
        return results
