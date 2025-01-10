import unittest
import sys

from mininet.net import Mininet
from mininet.node import OVSController
from mininet.log import setLogLevel

from playwright.sync_api import sync_playwright
from urllib.parse import urlencode
from pint import Quantity

from utils.topologies.SingleServerNetworkTopology import NetworkTopology
from utils.BandwidthController import BandwidthController
from utils.VideoPlayer import VideoPlayer
from utils.ProxyLogFileParser import ProxyLogFileParser

import logging
logger = logging.getLogger(__name__)

class TestBitrateAdaptation(unittest.TestCase):

    ROUTER_IP = "10.0.1.1"
    WEBSERVER_IP = "10.0.1.100"
    WEBSERVER_PORT = 8000
    WEBSERVER_CONTENT_PATH = "./www"
    PROXY_LOG_FILE_NAME = "proxy_log.txt"
    BITRATE_ADAPTATION_PROXY_IP = "10.0.2.100"
    BITRATE_ADAPTATION_PROXY_PORT = 9000
    ADAPTATION_GAIN = 0.5
    ADAPTATION_BITRATE_MULTIPLIER = 1.5
    CLIENT_IP = "10.0.3.100"
    PROXY_BASE_URL = f"http://{BITRATE_ADAPTATION_PROXY_IP}:{BITRATE_ADAPTATION_PROXY_PORT}/player.html"
    TEST_BANDWIDTH_BITRATE_MULTIPLIER = 1.8
    CHROMIUM_EXE_PATH = "/snap/bin/chromium"

    @classmethod
    def setUpClass(cls) -> None:
        cls._startEmulatedNetwork()
        cls._startWebServer()
        cls._startBitrateAdaptationProxyServer()
        cls._startBandwidthController()
        cls.logFileParser = ProxyLogFileParser(f"./{cls.PROXY_LOG_FILE_NAME}")
        cls._startBrowser()
        return super().setUpClass()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.playwright.stop()
        cls.webServerProcess.terminate()
        cls.webServerProcess.wait()
        cls.bitrateAdaptationProxyServerProcess.terminate()
        cls.bitrateAdaptationProxyServerProcess.wait()
        cls.net.stop()
        return super().tearDownClass()

    @classmethod
    def _startBrowser(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True, executable_path=cls.CHROMIUM_EXE_PATH)
        cls.browserContext = cls.browser.new_context()
        cls.browserContext.set_default_timeout(0) # Disable automatic request timeout

    @classmethod
    def _startEmulatedNetwork(cls):
        setLogLevel("info")
        cls.topology = NetworkTopology(
            webServerIp=cls.WEBSERVER_IP,
            bitrateAdaptationProxyIp=cls.BITRATE_ADAPTATION_PROXY_IP,
            clientIp=cls.CLIENT_IP,
            routerIp=cls.ROUTER_IP
        )
        cls.net = Mininet(topo=cls.topology, waitConnected=True)
        cls.net.addController(name="controller", controller=OVSController)
        cls.net.start()

    @classmethod
    def _startBandwidthController(cls):
        webServerLinks = cls.net.linksBetween(cls.net["webServer"], cls.net["router"])
        cls.bwController = BandwidthController(next(iter(webServerLinks)))

    @classmethod
    def _startWebServer(cls):
        cls.webServerProcess = cls.net["webServer"].popen([
                "./webserver.py",
                "--host", f"{cls.WEBSERVER_IP}",
                "--port", f"{cls.WEBSERVER_PORT}",
                "--content-path", f"{cls.WEBSERVER_CONTENT_PATH}",
            ],
            stdout=sys.stdout,
            stderr=sys.stderr
        )

    @classmethod
    def _startBitrateAdaptationProxyServer(cls):
        cls.bitrateAdaptationProxyServerProcess = cls.net["bitrateAdaptationProxy"].popen([
                "./miProxy",
                "--proxy-host", f"{cls.BITRATE_ADAPTATION_PROXY_IP}",
                "--proxy-port", f"{cls.BITRATE_ADAPTATION_PROXY_PORT}",
                "--upstream-server-host", f"{cls.WEBSERVER_IP}",
                "--upstream-server-port", f"{cls.WEBSERVER_PORT}",
                "--adaptation-gain", f"{cls.ADAPTATION_GAIN}",
                "--adaptation-bitrate-multiplier", f"{cls.ADAPTATION_BITRATE_MULTIPLIER}",
                "--log-file-name", f"{cls.PROXY_LOG_FILE_NAME}"

            ],
            stdout=sys.stdout,
            stderr=sys.stderr
        )

    def _makePlayerUrl(self, manifestPath):
        return self.PROXY_BASE_URL + "?" + urlencode({"manifest" : manifestPath})

    def _setBandwidth(self, newBandwidth):
        logger.info(f"[ {newBandwidth} ]")
        self.bwController.setBandwidth(newBandwidth)
        print()

    def _checkTargetBitrateReachedButNotExceeded(self, targetBitrate):
        logEntries = self.logFileParser.parseNewEntries()
        self.assertTrue(len(logEntries) > 0,
                        "Nothing written to the log")
        self.assertTrue(all(entry.bitrateChosen <= targetBitrate for entry in logEntries),
                        "Target bitrate exceeded")
        self.assertTrue(any(entry.bitrateChosen == targetBitrate for entry in logEntries),
                        "Target bitrate not reached")

    def _checkBitrateDowngraded(self, targetBitrate):
        logEntries = self.logFileParser.parseNewEntries()
        self.assertTrue(len(logEntries) > 0,
                        "Nothing written to the log")
        self.assertTrue(all(entry.bitrateChosen <= prevEntry.bitrateChosen for entry, prevEntry in zip(logEntries[1:], logEntries)),
                        "Bitrates are not monotonically decreasing")
        self.assertTrue(any(entry.bitrateChosen == targetBitrate for entry in logEntries[1:]),
                        "Target bitrate not reached")

    def test01_BitrateAdaptationSteadyState(self):
        """
            Basic bitrate adaptation tests

            Description:
                Set a fixed link bandwidth before opening the video player. Play
                the video for a few seconds and verify that the bitrate adaptation reached the
                highest supported bitrate for that bandwidth without exceeding it.

            Video:
                Wing It (2023) [https://studio.blender.org/films/wing-it/]

            @points: 24
        """

        VIDEO_MANIFEST_RELATIVE_PATH = "/wing_it/wing_it.m3u8"

        targetBitrate = Quantity(1300000, "bits / second")
        logger.info(f"Setting initial bandwidth to {self.TEST_BANDWIDTH_BITRATE_MULTIPLIER} * {targetBitrate} [240p]")
        self._setBandwidth(targetBitrate * self.TEST_BANDWIDTH_BITRATE_MULTIPLIER)
        url = self._makePlayerUrl(manifestPath=VIDEO_MANIFEST_RELATIVE_PATH)
        player = VideoPlayer(self.browserContext, hlsPlayerUrl=url)
        player.playVideoUntil(Quantity(25, "seconds"))
        player.close()
        self._checkTargetBitrateReachedButNotExceeded(targetBitrate)

        targetBitrate = Quantity(4000000, "bits / second")
        logger.info(f"Setting initial bandwidth to {self.TEST_BANDWIDTH_BITRATE_MULTIPLIER} * {targetBitrate} [480p]")
        self._setBandwidth(targetBitrate * self.TEST_BANDWIDTH_BITRATE_MULTIPLIER)
        player = VideoPlayer(self.browserContext, hlsPlayerUrl=url)
        player.playVideoUntil(Quantity(25, "seconds"))
        player.close()
        self._checkTargetBitrateReachedButNotExceeded(targetBitrate)

        targetBitrate = Quantity(13000000, "bits / second")
        logger.info(f"Setting initial bandwidth to {self.TEST_BANDWIDTH_BITRATE_MULTIPLIER} * {targetBitrate} [1080p]")
        self._setBandwidth(targetBitrate * self.TEST_BANDWIDTH_BITRATE_MULTIPLIER)
        player = VideoPlayer(self.browserContext, hlsPlayerUrl=url)
        player.playVideoUntil(Quantity(25, "seconds"))
        player.close()
        self._checkTargetBitrateReachedButNotExceeded(targetBitrate)

    def test02_BitrateAdaptationDynamic(self):
        """
            Dynamic bitrate adaptation test

            Description:
                Dynamically vary the link bandwidth while the video is actually playing.
                Verify that the bitrate adaptation responds correctly in all cases (i.e.
                by increasing the bitrate when enough bandwidth is available to support
                a higher bitrate, and downgrading it when the bandwidth drops to a level
                where it can no longer sustain the current one).

            Video:
                Charge (2022) [https://studio.blender.org/films/charge/]

            @points: 10
        """

        VIDEO_MANIFEST_RELATIVE_PATH = "/charge/charge.m3u8"

        targetBitrate = Quantity(3000000, "bits / second")
        logger.info(f"Setting initial bandwidth to {self.TEST_BANDWIDTH_BITRATE_MULTIPLIER} * {targetBitrate} [240p]")
        self._setBandwidth(targetBitrate * self.TEST_BANDWIDTH_BITRATE_MULTIPLIER)
        url = self._makePlayerUrl(manifestPath=VIDEO_MANIFEST_RELATIVE_PATH)
        player = VideoPlayer(self.browserContext, hlsPlayerUrl=url)
        player.playVideoUntil(Quantity(10, "seconds"))
        self._checkTargetBitrateReachedButNotExceeded(targetBitrate)

        targetBitrate = Quantity(6000000, "bits / second")
        logger.info(f"Increasing bandwidth to {self.TEST_BANDWIDTH_BITRATE_MULTIPLIER} * {targetBitrate} [360p]")
        self._setBandwidth(targetBitrate * self.TEST_BANDWIDTH_BITRATE_MULTIPLIER)
        player.playVideoFor(Quantity(20, "seconds"))
        self._checkTargetBitrateReachedButNotExceeded(targetBitrate)

        targetBitrate = Quantity(24000000, "bits / second")
        logger.info(f"Increasing bandwidth to {self.TEST_BANDWIDTH_BITRATE_MULTIPLIER} * {targetBitrate} [720p]")
        self._setBandwidth(targetBitrate * self.TEST_BANDWIDTH_BITRATE_MULTIPLIER)
        player.playVideoFor(Quantity(25, "seconds"))
        self._checkTargetBitrateReachedButNotExceeded(targetBitrate)

        targetBitrate = Quantity(10000000, "bits / second")
        logger.info(f"Decreasing bandwidth to {self.TEST_BANDWIDTH_BITRATE_MULTIPLIER} * {targetBitrate} [480p]")
        self._setBandwidth(targetBitrate * self.TEST_BANDWIDTH_BITRATE_MULTIPLIER)
        player.playVideoFor(Quantity(20, "seconds"))
        self._checkBitrateDowngraded(targetBitrate)

        targetBitrate = Quantity(3000000, "bits / second")
        logger.info(f"Decreasing bandwidth to {self.TEST_BANDWIDTH_BITRATE_MULTIPLIER} * {targetBitrate} [240p]")
        self._setBandwidth(targetBitrate * self.TEST_BANDWIDTH_BITRATE_MULTIPLIER)
        player.playVideoFor(Quantity(20, "seconds"))
        self._checkBitrateDowngraded(targetBitrate)

        targetBitrate = Quantity(40000000, "bits / second")
        logger.info(f"Increasing bandwidth to {self.TEST_BANDWIDTH_BITRATE_MULTIPLIER} * {targetBitrate} [1080p]")
        self._setBandwidth(targetBitrate * self.TEST_BANDWIDTH_BITRATE_MULTIPLIER)
        player.playVideoFor(Quantity(30, "seconds"))
        self._checkTargetBitrateReachedButNotExceeded(targetBitrate)
        player.close()
