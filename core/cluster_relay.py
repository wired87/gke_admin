

class ClusterRelayCreator:

    """
    Creytes necessary infrastructure
    for a clsuter to expose it to the
    outer world
    """
    def __init__(
            self,
            client,
            core,
            ip_manager
    ):
        self.client=client
        self.core=core
        self.ip_manager=ip_manager




    def create_relay_resources(self):
        """
        Create
        LoadBalancer
        Ingress controller

        Connect IP though DNS to Domain
        """

