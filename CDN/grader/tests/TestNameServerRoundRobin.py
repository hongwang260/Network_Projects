from itertools import cycle, islice
import unittest
import subprocess
import tempfile
import dns.resolver

class TestNameServerRoundRobin(unittest.TestCase):

    NAMESERVER_IP = "127.0.0.1"
    NAMESERVER_PORT = 9500
    NAMESERVER_DOMAIN_NAME = "video.cdn.assignment2.test"
    TEST_IPS = ["73.220.114.204", "166.238.236.185", "216.68.239.161"]

    @classmethod
    def setUpClass(cls) -> None:
        cls.ipListFile = tempfile.NamedTemporaryFile(mode="w", delete_on_close=True)
        cls.ipListFile.writelines(ipAddress + "\n" for ipAddress in cls.TEST_IPS)
        cls.ipListFile.flush()
        cls.nameserverProcess = cls._startNameServerProcess(cls.ipListFile.name)
        cls.resolver = dns.resolver.Resolver(configure=False)
        cls.resolver.nameservers = [f"{cls.NAMESERVER_IP}"]
        cls.resolver.port = cls.NAMESERVER_PORT
        return super().setUpClass()

    @classmethod
    def _startNameServerProcess(cls, roundRobinIpListFilePath):
        return subprocess.Popen([
            "./nameserver",
            "--ip", f"{cls.NAMESERVER_IP}",
            "--port", f"{cls.NAMESERVER_PORT}",
            "--domain", f"{cls.NAMESERVER_DOMAIN_NAME}",
            "--round-robin-ip-list-file-path", f"{roundRobinIpListFilePath}"
        ])

    @classmethod
    def tearDownClass(cls) -> None:
        cls.nameserverProcess.terminate()
        cls.nameserverProcess.wait()
        return super().tearDownClass()

    def test01_DomainNameResolutionOk(self):
        """
            Test successful domain name resolution

            Description:
                Emulate sending a few DNS queries. Verify that the nameserver returns the
                configured IP addresses in a round-robin fashion.

            @points: 10
        """
        numRepetitions = 3
        for expectedIpAddress in islice(cycle(self.TEST_IPS), numRepetitions * len(self.TEST_IPS)):
            returnedIpAddress = self._queryNameServer(self.NAMESERVER_DOMAIN_NAME)
            self.assertEqual(returnedIpAddress, expectedIpAddress)

    def test02_DomainNameDoesNotExist(self):
        """
            Test failed domain name resolution (domain name does not exist)

            Description:
                Emulate sending a DNS query for a domain name that the nameserver
                cannot resolve. Verify that the nameserver responds appropriately.

            @points: 2
        """
        self.assertRaises(dns.resolver.NXDOMAIN, self._queryNameServer, "some.other.domain")

    def _queryNameServer(self, domainName):
        answer = self.resolver.resolve(domainName)
        return str(next(iter(answer)))
