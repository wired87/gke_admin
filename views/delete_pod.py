import os

from django.views import View
from django.http import JsonResponse
import subprocess

from gke_admin.core.build_admin import GKEBuildAdmin

# Importiere deine GKEBuildAdmin-Klasse

class DeletePodView(View):
    """
    Ein View, der einen GKE-Pod mit einem bestimmten Namen löscht.
    """

    def delete(self, request, *args, **kwargs):
        pod_names: list = kwargs.get('pod_names')
        user_id: list = kwargs.get('user_id')
        cluster_name = kwargs.get('cluster_name')

        if not pod_names or not isinstance(pod_names, list) or not len(pod_names):
            return JsonResponse({'error': 'Pod name not provided'}, status=400)

        admin = GKEBuildAdmin(
            gcp_project_id=os.environ["GCP_PROJECT_ID"],
            cluster_domain=os.environ["CLUSTER_DOMAIN"],
            cluster_name=os.environ["GKE_SIM_CLUSTER_NAME"],
            cluster_port=os.environ["CLUSTER_PORT"],
            cluster_subdomain=os.environ["CLUSTER_SUB_DOMAIN"],
        )

        try:
            # Authentifizierung beim Cluster
            admin.authenticate_cluster()

            admin.delelte_pods(pod_names)

            return JsonResponse({'message': f'Pods successfully deleted'}, status=200)

        except subprocess.CalledProcessError as e:
            # Fehler behandeln, wenn der Pod nicht existiert oder ein anderer Fehler auftritt
            return JsonResponse({'error': f'Failed to delete pod: {e.stderr.strip()}'}, status=500)
        except Exception as e:
            # Unerwartete Fehler
            return JsonResponse({'error': f'An unexpected error occurred: {str(e)}'}, status=500)