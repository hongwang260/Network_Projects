import unittest
import subprocess
import tempfile
import dns.resolver

class TestNameServerGeolocation(unittest.TestCase):

    NAMESERVER_IP = "127.0.0.1"
    NAMESERVER_PORT = 9500
    NAMESERVER_DOMAIN_NAME = "video.cdn.assignment2.test"

    @classmethod
    def setUpClass(cls) -> None:
        cls.resolver = dns.resolver.Resolver(configure=False)
        cls.resolver.nameservers = [cls.NAMESERVER_IP]
        cls.resolver.port = cls.NAMESERVER_PORT
        return super().setUpClass()

    def _startNameServerProcess(cls, networkTopologyFilePath):
        return subprocess.Popen([
            "./nameserver",
            "--ip", f"{cls.NAMESERVER_IP}",
            "--port", f"{cls.NAMESERVER_PORT}",
            "--domain", f"{cls.NAMESERVER_DOMAIN_NAME}",
            "--network-topology-file-path", f"{networkTopologyFilePath}"
        ])

    def test01_DomainNameResolutionOk(self):
        """
            Test successful domain name resolution

            Description:
                Emulate sending a DNS query from multiple clients. For each client,
                verify that the nameserver returned the IP address of the server that
                is closest to it.

            @points: 10
        """
        TOPOLOGY =[
            "NUM_NODES: 6",
            "0 CLIENT 10.0.0.1",
            "1 CLIENT 10.0.0.2",
            "2 SWITCH NO_IP",
            "3 SWITCH NO_IP",
            "4 SERVER 10.0.0.3",
            "5 SERVER 10.0.0.4",
            "NUM_LINKS: 5",
            "0 2 1",
            "1 2 1",
            "2 3 1",
            "3 4 6",
            "3 5 1"
        ]
        networkTopologyFile = tempfile.NamedTemporaryFile(mode="w", delete_on_close=True)
        networkTopologyFile.writelines(line + "\n" for line in TOPOLOGY)
        networkTopologyFile.flush()
        nameServerProcess = self._startNameServerProcess(networkTopologyFile.name)
        self._createFakeSourceInterface("10.0.0.1")
        self.assertEqual(self._queryNameServer(self.NAMESERVER_DOMAIN_NAME, sourceIp="10.0.0.1"), "10.0.0.4")
        self._createFakeSourceInterface("10.0.0.2")
        self.assertEqual(self._queryNameServer(self.NAMESERVER_DOMAIN_NAME, sourceIp="10.0.0.2"), "10.0.0.4")
        nameServerProcess.terminate()
        nameServerProcess.wait()

    def test02_NoPathToAnyServer(self):
        """
            Test failed domain name resolution (no path to server)

            Description:
                Emulate sending a DNS query from a client that has no path to any
                server in the topology. Verify that no answers are returned.

            @points: 2
        """
        TOPOLOGY =[
            # Client 0 has no path to servers
            "NUM_NODES: 6",
            "0 CLIENT 10.0.0.1",
            "1 CLIENT 10.0.0.2",
            "2 SWITCH NO_IP",
            "3 SWITCH NO_IP",
            "4 SERVER 10.0.0.3",
            "5 SERVER 10.0.0.4",
            "NUM_LINKS: 4",
            "1 2 1",
            "2 3 1",
            "3 4 6",
            "3 5 1"
        ]
        networkTopologyFile = tempfile.NamedTemporaryFile(mode="w", delete_on_close=True)
        networkTopologyFile.writelines(line + "\n" for line in TOPOLOGY)
        networkTopologyFile.flush()
        nameServerProcess = self._startNameServerProcess(networkTopologyFile.name)
        self._createFakeSourceInterface("10.0.0.1")
        self.assertRaises(dns.resolver.NoAnswer, self._queryNameServer, self.NAMESERVER_DOMAIN_NAME, sourceIp="10.0.0.1")
        nameServerProcess.terminate()
        nameServerProcess.wait()

    def test03_DomainNameDoesNotExist(self):
        """
            Test failed domain name resolution (domain name does not exist)

            Description:
                Emulate sending a DNS query for a domain name that the nameserver
                cannot resolve. Verify that the nameserver responds appropriately.

            @points: 2
        """
        TOPOLOGY =[
            "NUM_NODES: 6",
            "0 CLIENT 10.0.0.1",
            "1 CLIENT 10.0.0.2",
            "2 SWITCH NO_IP",
            "3 SWITCH NO_IP",
            "4 SERVER 10.0.0.3",
            "5 SERVER 10.0.0.4",
            "NUM_LINKS: 5",
            "0 2 1",
            "1 2 1",
            "2 3 1",
            "3 4 6",
            "3 5 1"
        ]
        networkTopologyFile = tempfile.NamedTemporaryFile(mode="w", delete_on_close=True)
        networkTopologyFile.writelines(line + "\n" for line in TOPOLOGY)
        networkTopologyFile.flush()
        nameServerProcess = self._startNameServerProcess(networkTopologyFile.name)
        self._createFakeSourceInterface("10.0.0.1")
        self.assertRaises(dns.resolver.NXDOMAIN, self._queryNameServer, "some.other.domain", sourceIp="10.0.0.1")
        nameServerProcess.terminate()
        nameServerProcess.wait()

    def _queryNameServer(self, domainName, sourceIp):
        answer = self.resolver.resolve(domainName, source=sourceIp)
        return str(next(iter(answer)))

    def _createFakeSourceInterface(self, ipAddress):
        subprocess.run(f"ip addr add {ipAddress} dev lo", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
