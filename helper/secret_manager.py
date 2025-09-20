import os
import random
import time

from OpenSSL import crypto
from kubernetes import client
from kubernetes.client.exceptions import ApiException


class SecretManager:
    def __init__(
            self,
            core,
            apps,
            cluster_domain,
            namespace=None,
            secret_name=None
    ):
        """
        Initialize connection to Kubernetes.
        If kubeconfig is None, use in-cluster config (for Pods).
        """
        self.core = core
        self.namespace = namespace
        self.name = secret_name
        self.cluster_domain = cluster_domain
        self.san_list = [cluster_domain]
        self.cfg_path =r"C:\Users\wired\OneDrive\Desktop\BestBrain\utils\san.cnf" if os.name == "nt" else "san.cnf"


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
            crt_data, key_data = self.generate_self_signed_cert_with_san()
            secret_name = self.create_tls_secret(
                name,
                namespace,
                crt_data,
                key_data
            )
            print("finished secret_process")
            return secret_name
        except Exception as e:
            print(f"Err check_create_secret: {e}")

    def generate_self_signed_cert_with_san(self, bits=2048, days=365):
        key = crypto.PKey()
        key.generate_key(crypto.TYPE_RSA, bits)

        cert = crypto.X509()
        cert.set_serial_number(int(time.time()) + random.randint(0, 100000))
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(days * 24 * 60 * 60)

        # Subject
        subject = cert.get_subject()
        subject.CN = self.san_list[0]  # erstes SAN als CN
        subject.O = "MyOrg"
        subject.C = "DE"

        cert.set_issuer(subject)
        cert.set_pubkey(key)

        # Extensions
        san_string = ", ".join(f"DNS:{name}" for name in self.san_list)
        extensions = [
            crypto.X509Extension(b"basicConstraints", False, b"CA:FALSE"),
            crypto.X509Extension(b"keyUsage", False, b"digitalSignature,keyEncipherment"),
            crypto.X509Extension(b"extendedKeyUsage", False, b"serverAuth"),
            crypto.X509Extension(b"subjectAltName", False, san_string.encode("utf-8")),
        ]
        cert.add_extensions(extensions)

        cert.sign(key, "sha256")

        with open(self.cert_path, "wt") as f:
            crt_data = crypto.dump_certificate(crypto.FILETYPE_PEM, cert).decode("utf-8")
            f.write(crt_data)

        with open(self.key_path, "wt") as f:
            key_data = crypto.dump_privatekey(crypto.FILETYPE_PEM, key).decode("utf-8")
            f.write(key_data)

        print(f"✅ Certificate saved at {self.cert_path}")
        print(f"✅ Key saved at {self.key_path}")
        return crt_data, key_data

    # Example usage:
    # generate_self_signed_cert_with_san("cert.pem", "key.pem", san_list=["cluster.clusterexpress.com", "localhost"])







    def create_tls_secret(
            self,
            name,
            namespace,
            crt_data,
            key_data
    ):
        """
        Create or replace a TLS secret in the given namespace.
        """
        secret = client.V1Secret(
            api_version="v1",
            kind="Secret",
            metadata=client.V1ObjectMeta(
                name=name,
                #namespace=namespace
            ),
            type="kubernetes.io/tls",
            string_data={
                "tls.crt": crt_data,
                "tls.key": key_data,
            }
        )
        try:
            self.core.create_namespaced_secret(
                namespace,
                secret
            )
            print(f"✅ Secret {name} created in -n {namespace}")
        except Exception as e:
            print(f"♻️ Secret {name} replaced in {namespace}: {e}")

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
