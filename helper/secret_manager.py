import os

from OpenSSL import crypto
from kubernetes import client
from kubernetes.client.exceptions import ApiException


class SecretManager:
    def __init__(
            self,
            core,
            cluster_domain,
            namespace=None,
            secret_name=None
    ):
        """
        Initialize connection to Kubernetes.
        If kubeconfig is None, use in-cluster config (for Pods).
        """
        self.core = core
        self.namespace=namespace
        self.name=secret_name
        self.cluster_domain = cluster_domain

        # Key paths
        self.out_dir = r"C:\Users\wired\OneDrive\Desktop\BestBrain\utils\_kubernetes\secrets" if os.name == "nt" else "utils/_kubernetes/secrets/"
        os.makedirs(self.out_dir, exist_ok=True)

        self.key_path = os.path.join(self.out_dir, "privkey.pem")
        self.cert_path = os.path.join(self.out_dir, "fullchain.pem")

    def check_create_secret(self, name=None, namespace=None):
        print("===============SECRET PROCESS=================")
        namespace = namespace or self.namespace
        name = name or self.name

        try:
            secret = self.get_secret(name, namespace)
            if secret is not None:
                print(f"Secret {self.name} already exists")
                return
            print("start check_create_secret")
            self.generate_selfsigned_cert()
            secret_name = self.create_tls_secret(
                name,
                namespace)
            print("finished secret_process")
            return secret_name
        except Exception as e:
            print(f"Err check_create_secret: {e}")

    def generate_selfsigned_cert(
            self,
            bits=2048,
            days=365,
    ):
        """
        Generate a self-signed certificate + private key with pyOpenSSL,
        and save them under out_dir.
        """
        # Create key pair
        key = crypto.PKey()
        key.generate_key(crypto.TYPE_RSA, bits)

        # Create self-signed certificate
        cert = crypto.X509()
        cert.get_subject().CN = self.cluster_domain
        cert.set_serial_number(1000)
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(days * 24 * 60 * 60)
        cert.set_issuer(cert.get_subject())
        cert.set_pubkey(key)
        cert.sign(key, "sha256")

        with open(self.cert_path, "wt") as f:
            f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("utf-8"))

        with open(self.key_path, "wt") as f:
            f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, key).decode("utf-8"))

        print(f"✅ Certificate saved at {self.cert_path}")
        print(f"✅ Key saved at {self.key_path}")

    def create_tls_secret(self, name, namespace="default"):
        """
        Create or replace a TLS secret in the given namespace.
        """
        with open(self.cert_path, "rb") as f:
            crt_data = f.read()
        with open(self.key_path, "rb") as f:
            key_data = f.read()

        secret = client.V1Secret(
            api_version="v1",
            kind="Secret",
            metadata=client.V1ObjectMeta(
                name=name,
                namespace=namespace
            ),
            type="kubernetes.io/tls",
            string_data={   # string_data lets API do base64 internally
                "tls.crt": crt_data.decode("utf-8"),
                "tls.key": key_data.decode("utf-8")
            }
        )

        try:
            self.core.create_namespaced_secret(
                namespace, secret)
            print(f"✅ Secret {name} created in {namespace}")
        except ApiException as e:
            if e.status == 409:
                self.core.replace_namespaced_secret(name, namespace, secret)
                print(f"♻️ Secret {name} replaced in {namespace}")
            else:
                raise

    def get_secret(self, name, namespace):
        """
        Fetch a secret by name.
        """
        try:
            sec = self.core.read_namespaced_secret(name, namespace)
            print(f"🔎 Secret {name} found in {namespace}")
            return sec
        except ApiException as e:
            if e.status == 404:
                print(f"❌ Secret {name} not found in {namespace}")
                return None
            raise

    def delete_secret(self, namespace, name):
        """
        Delete a secret.
        """
        try:
            self.core.delete_namespaced_secret(name, namespace)
            print(f"🗑️ Secret {name} deleted from {namespace}")
        except ApiException as e:
            if e.status == 404:
                print(f"⚠️ Secret {name} not found in {namespace}")
            else:
                raise
