import unittest
import sys
import tempfile
import time

from mininet.net import Mininet
from mininet.node import OVSController
from mininet.log import setLogLevel

from playwright.sync_api import sync_playwright
from urllib.parse import urlencode
from pint import Quantity

from utils.topologies.MultipleServersNetworkTopology import NetworkTopology
from utils.BandwidthController import BandwidthController
from utils.VideoPlayer import VideoPlayer
from utils.NameserverLogFileParser import NameserverLogFileParser
from utils.ProxyLogFileParser import ProxyLogFileParser

import logging
logger = logging.getLogger(__name__)

class IntegrationGeolocation(unittest.TestCase):

    ROUTER_IP = "10.0.1.1"
    WEBSERVER1_IP = "10.0.1.100"
    WEBSERVER1_CONTENT_PATH = "./www"
    WEBSERVER2_IP = "10.0.2.100"
    WEBSERVER2_CONTENT_PATH = "./www"
    WEBSERVER_PORT = 8000
    NAMESERVER_IP = "10.0.3.100"
    NAMESERVER_PORT = 53
    NAMESERVER_DOMAIN_NAME = "video.cdn.assignment2.test"
    BITRATE_ADAPTATION_PROXY1_IP = "10.0.4.100"
    BITRATE_ADAPTATION_PROXY1_PORT = 9000
    BITRATE_ADAPTATION_PROXY2_IP = "10.0.5.100"
    BITRATE_ADAPTATION_PROXY2_PORT = 9000
    ADAPTATION_GAIN = 0.33
    ADAPTATION_BITRATE_MULTIPLIER = 1.5
    CLIENT_IP = "10.0.6.100"
    NAMESERVER_LOG_FILE_NAME = "nameserver_log.txt"
    PROXY1_LOG_FILE_NAME = "proxy1_log.txt"
    PROXY2_LOG_FILE_NAME = "proxy2_log.txt"
    PROXY1_BASE_URL = f"http://{BITRATE_ADAPTATION_PROXY1_IP}:{BITRATE_ADAPTATION_PROXY1_PORT}/player.html"
    PROXY2_BASE_URL = f"http://{BITRATE_ADAPTATION_PROXY2_IP}:{BITRATE_ADAPTATION_PROXY2_PORT}/player.html"
    TEST_BANDWIDTH_BITRATE_MULTIPLIER = 1.8

    @classmethod
    def setUpClass(cls) -> None:
        cls._startEmulatedNetwork()
        cls._startWebServers()
        cls._startNameServer()
        time.sleep(1) # Fix
        cls._startBitrateAdaptationProxyServers()
        cls._startBandwidthControllers()
        time.sleep(1) # Fix
        cls.nameserverLogFileParser = NameserverLogFileParser(f"./{cls.NAMESERVER_LOG_FILE_NAME}")
        cls.proxy1LogFileParser = ProxyLogFileParser(f"./{cls.PROXY1_LOG_FILE_NAME}")
        cls.proxy2LogFileParser = ProxyLogFileParser(f"./{cls.PROXY2_LOG_FILE_NAME}")
        cls._startBrowser()
        return super().setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.playwright.stop()
        cls.webServer1Process.terminate()
        # cls.webServer2Process.wait()
        cls.nameServerProcess.terminate()
        # cls.nameServerProcess.wait()
        cls.bitrateAdaptationProxyServer1Process.terminate()
        # cls.bitrateAdaptationProxyServer2Process.wait()
        cls.net.stop()
        return super().tearDownClass()

    @classmethod
    def _startBrowser(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True, executable_path="/snap/bin/chromium")
        cls.browserContext = cls.browser.new_context()
        cls.browserContext.set_default_timeout(0) # Disable automatic request timeout

    @classmethod
    def _startEmulatedNetwork(cls):
        setLogLevel("info")
        topology = NetworkTopology(
            webServer1Ip=cls.WEBSERVER1_IP,
            webServer2Ip=cls.WEBSERVER2_IP,
            nameServerIp=cls.NAMESERVER_IP,
            bitrateAdaptationProxy1Ip=cls.BITRATE_ADAPTATION_PROXY1_IP,
            bitrateAdaptationProxy2Ip=cls.BITRATE_ADAPTATION_PROXY2_IP,
            clientIp=cls.CLIENT_IP,
            routerIp=cls.ROUTER_IP
        )
        cls.net = Mininet(topo=topology, waitConnected=True)
        cls.net.addController(name="controller", controller=OVSController)
        cls.net.start()

    @classmethod
    def _startBandwidthControllers(cls):
        webServer1Links = cls.net.linksBetween(cls.net["webServer1"], cls.net["router"])
        webServer2Links = cls.net.linksBetween(cls.net["webServer2"], cls.net["router"])
        cls.webServer1BwController = BandwidthController(next(iter(webServer1Links)))
        cls.webServer2BwController = BandwidthController(next(iter(webServer2Links)))

    @classmethod
    def _startWebServers(cls):
        cls.webServer1Process = cls.net["webServer1"].popen([
                "./webserver.py",
                "--host", f"{cls.WEBSERVER1_IP}",
                "--port", f"{cls.WEBSERVER_PORT}",
                "--content-path", f"{cls.WEBSERVER1_CONTENT_PATH}",
            ],
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        cls.webServer2Process = cls.net["webServer2"].popen([
                "./webserver.py",
                "--host", f"{cls.WEBSERVER2_IP}",
                "--port", f"{cls.WEBSERVER_PORT}",
                "--content-path", f"{cls.WEBSERVER2_CONTENT_PATH}",
            ],
            stdout=sys.stdout,
            stderr=sys.stderr
        )

    @classmethod
    def _startNameServer(cls):
        TOPOLOGY =[
            "NUM_NODES: 6",
            f"0 CLIENT {cls.BITRATE_ADAPTATION_PROXY1_IP}",
            f"1 CLIENT {cls.BITRATE_ADAPTATION_PROXY2_IP}",
            f"2 SWITCH NO_IP",
            f"3 SWITCH NO_IP",
            f"4 SERVER {cls.WEBSERVER1_IP}",
            f"5 SERVER {cls.WEBSERVER2_IP}",
            f"NUM_LINKS: 5",
            f"0 2 1",
            f"1 2 1",
            f"2 3 1",
            f"3 4 6",
            f"3 5 1"
        ]
        cls.networkTopologyFile = tempfile.NamedTemporaryFile(mode="w", delete_on_close=True)
        cls.networkTopologyFile.writelines(ipAddress + "\n" for ipAddress in TOPOLOGY)
        cls.networkTopologyFile.flush()
        cls.nameServerProcess = cls.net["nameServer"].popen([
                "./nameserver",
                "--ip", f"{cls.NAMESERVER_IP}",
                "--port", f"{cls.NAMESERVER_PORT}",
                "--domain", f"{cls.NAMESERVER_DOMAIN_NAME}",
                "--log-file-name", f"{cls.NAMESERVER_LOG_FILE_NAME}",
                "--network-topology-file-path", f"{cls.networkTopologyFile.name}"
            ],
            stdout=sys.stdout,
            stderr=sys.stderr
        )

    @classmethod
    def _startBitrateAdaptationProxyServers(cls):
        cls.bitrateAdaptationProxyServer1Process = cls.net["bitrateAdaptationProxy1"].popen([
                "./miProxy",
                "--proxy-host", f"{cls.BITRATE_ADAPTATION_PROXY1_IP}",
                "--proxy-port", f"{cls.BITRATE_ADAPTATION_PROXY1_PORT}",
                "--upstream-server-host", f"{cls.NAMESERVER_DOMAIN_NAME}",
                "--upstream-server-port", f"{cls.WEBSERVER_PORT}",
                "--adaptation-gain", f"{cls.ADAPTATION_GAIN}",
                "--adaptation-bitrate-multiplier", f"{cls.ADAPTATION_BITRATE_MULTIPLIER}",
                "--nameserver-ip", f"{cls.NAMESERVER_IP}",
                "--nameserver-port", f"{cls.NAMESERVER_PORT}",
                "--log-file-name", f"{cls.PROXY1_LOG_FILE_NAME}"
            ],
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        cls.bitrateAdaptationProxyServer2Process = cls.net["bitrateAdaptationProxy2"].popen([
                "./miProxy",
                "--proxy-host", f"{cls.BITRATE_ADAPTATION_PROXY2_IP}",
                "--proxy-port", f"{cls.BITRATE_ADAPTATION_PROXY2_PORT}",
                "--upstream-server-host", f"{cls.NAMESERVER_DOMAIN_NAME}",
                "--upstream-server-port", f"{cls.WEBSERVER_PORT}",
                "--adaptation-gain", f"{cls.ADAPTATION_GAIN}",
                "--adaptation-bitrate-multiplier", f"{cls.ADAPTATION_BITRATE_MULTIPLIER}",
                "--nameserver-ip", f"{cls.NAMESERVER_IP}",
                "--nameserver-port", f"{cls.NAMESERVER_PORT}",
                "--log-file-name", f"{cls.PROXY2_LOG_FILE_NAME}"
            ],
            stdout=sys.stdout,
            stderr=sys.stderr
        )

    def _makePlayerUrl(self, baseUrl, manifestPath):
        return baseUrl + "?" + urlencode({"manifest" : manifestPath})

    def _setBandwidth(self, webServer, newBandwidth):
        logger.info(f"[ {newBandwidth} ]")
        match webServer:
            case "webServer1":
                self.webServer1BwController.setBandwidth(newBandwidth)
            case "webServer2":
                self.webServer2BwController.setBandwidth(newBandwidth)
            case _:
                raise RuntimeError
        print()

    def _checkTargetBitrateReachedButNotExceeded(self, proxy, targetBitrate):
        match proxy:
            case "proxy1":
                logEntries = self.proxy1LogFileParser.parseNewEntries()
            case "proxy2":
                logEntries = self.proxy2LogFileParser.parseNewEntries()
            case _:
                raise RuntimeError
        self.assertTrue(len(logEntries) > 0,
                        "Nothing written to the log")
        self.assertTrue(all(entry.bitrateChosen <= targetBitrate for entry in logEntries),
                        "Target bitrate exceeded")
        self.assertTrue(any(entry.bitrateChosen == targetBitrate for entry in logEntries),
                        "Target bitrate not reached")

    def test01_CheckServerMapping(self):
        """
            For each client, check that the servers were assigned correctly
            according to the shortest path in the topology.

            @points: 10
        """
        logEntries = self.nameserverLogFileParser.parseNewEntries()
        self.assertTrue(len(logEntries) == 2)
        for entry in logEntries:
            self.assertTrue(entry.clientIP in [self.BITRATE_ADAPTATION_PROXY1_IP, self.BITRATE_ADAPTATION_PROXY2_IP])
            self.assertEqual(entry.domainName.rstrip("."), self.NAMESERVER_DOMAIN_NAME)
            self.assertEqual(entry.answers, self.WEBSERVER2_IP)

    def test02_StreamFromServer1(self):
        """
            Check that we are able to successfully stream from the first proxy.

            Video:
                Wing It (2023) [https://studio.blender.org/films/wing-it/]

            @points: 10
        """
        VIDEO_MANIFEST_RELATIVE_PATH = "/wing_it/wing_it.m3u8"
        url = self._makePlayerUrl(baseUrl=self.PROXY1_BASE_URL, manifestPath=VIDEO_MANIFEST_RELATIVE_PATH)
        targetBitrate = Quantity(4000000, "bits / second")
        logger.info(f"Setting initial bandwidth to {self.TEST_BANDWIDTH_BITRATE_MULTIPLIER} * {targetBitrate} [480p]")
        self._setBandwidth("webServer2", targetBitrate * self.TEST_BANDWIDTH_BITRATE_MULTIPLIER)
        player = VideoPlayer(self.browserContext, hlsPlayerUrl=url)
        player.playVideoUntil(Quantity(20, "seconds"))
        self._checkTargetBitrateReachedButNotExceeded("proxy1", targetBitrate)
        player.close()

    def test03_StreamFromServer2(self):
        """
            Check that we are able to successfully stream from the second proxy.

            Video:
                Charge (2022) [https://studio.blender.org/films/charge/]

            @points: 10
        """
        VIDEO_MANIFEST_RELATIVE_PATH = "/charge/charge.m3u8"
        url = self._makePlayerUrl(baseUrl=self.PROXY2_BASE_URL, manifestPath=VIDEO_MANIFEST_RELATIVE_PATH)
        targetBitrate = Quantity(24000000, "bits / second")
        logger.info(f"Setting initial bandwidth to {self.TEST_BANDWIDTH_BITRATE_MULTIPLIER} * {targetBitrate} [720p]")
        self._setBandwidth("webServer2", targetBitrate * self.TEST_BANDWIDTH_BITRATE_MULTIPLIER)
        player = VideoPlayer(self.browserContext, hlsPlayerUrl=url)
        player.playVideoUntil(Quantity(20, "seconds"))
        self._checkTargetBitrateReachedButNotExceeded("proxy2", targetBitrate)
        player.close()
