#!/usr/bin/env python3.12

import time
import sys
import curses
import subprocess
import threading
import os

from utils.topologies.SingleServerNetworkTopology import NetworkTopology
from utils.BandwidthController import BandwidthController
from utils.CursesWindowIO import CursesWindowIO
from utils.CursesPrompt import CursesPrompt

from mininet.net import Mininet
from mininet.node import OVSController
from pint import Quantity
from shutil import copy

class Application:

    ROUTER_IP = "10.0.1.1"

    WEB_SERVER_IP = "10.0.1.100"
    WEB_SERVER_PORT = 8000
    WEB_SERVER_CONTENT_PATH = "www"

    ADAPTATION_PROXY_IP = "10.0.2.100"
    ADAPTATION_PROXY_PORT = 9000
    ADAPTATION_GAIN = 0.35
    ADAPTATION_BITRATE_MULTIPLIER = 1.5

    CLIENT_IP = "10.0.3.100"

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.initializeScreen()
        self.setupWindows()
        self.setupIORedirection()
        self.startMininet()
        self.startWebServer()
        self.startBitrateAdaptationProxy()
        self.verifyInitializationSuccessful()
        try:
            self.handleUserInput()
        except KeyboardInterrupt:
            print("\nCTRL+C pressed. Shutting down...")
        self.promptWindow.clear()
        self.promptWindow.refresh()
        self.net.stop()

    def initializeScreen(self):
        curses.start_color()
        curses.use_default_colors()
        self.stdscr.clear()
        self.height, self.width = self.stdscr.getmaxyx()

    def refreshScreen(self):
        self.stdscr.refresh()

    def setupWindows(self):
        spacingBetweenWindows = 1
        promptWindowHeight = 1
        promptWindowWidth = self.width
        promptWindowPosition = (self.height - promptWindowHeight, 0)
        outputWindowHeight = self.height - promptWindowHeight - spacingBetweenWindows
        outputWindowWidth = self.width
        outputWindowPosition = (0, 0)
        # Create prompt window
        self.promptWindow = self.stdscr.subwin(promptWindowHeight, promptWindowWidth, *promptWindowPosition)
        # Create output window
        self.outputWindow = self.stdscr.subwin(outputWindowHeight, outputWindowWidth, *outputWindowPosition)
        self.outputWindow.scrollok(True)

    def readStreamToOutputWindow(self, proc, stream):
        # Read output from the process and display it in the output window
        while True:
            output = getattr(proc, stream).readline()
            if output == b"" and proc.poll() is not None:
                break
            if output:
                self.outputWindow.addstr(output.decode("utf-8"))
                self.outputWindow.refresh()
                self.promptWindow.refresh()  # Refresh the prompt window to keep the cursor at the bottom

    def setupIORedirection(self):
        # Redirect stdout/stderr to output window
        sys.stdout = CursesWindowIO(self.outputWindow)
        sys.stderr = CursesWindowIO(self.outputWindow)

    def startMininet(self):
        self.topology = NetworkTopology(
            routerIp=self.ROUTER_IP,
            webServerIp=self.WEB_SERVER_IP,
            bitrateAdaptationProxyIp=self.ADAPTATION_PROXY_IP,
            clientIp=self.CLIENT_IP
        )
        self.net = Mininet(topo=self.topology, waitConnected=True)
        self.net.addController(name="controller", controller=OVSController)
        self.net.start()

    def startWebServer(self):
        self.webServer = self.net["webServer"].popen([
                "./webserver.py",
                "--host", f"{self.WEB_SERVER_IP}",
                "--port", f"{self.WEB_SERVER_PORT}",
                "--content-path", f"{self.WEB_SERVER_CONTENT_PATH}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.startOutputReaderThreads(self.webServer)

    def startBitrateAdaptationProxy(self):
        self.miProxy = self.net["bitrateAdaptationProxy"].popen([
                "./miProxy",
                "--proxy-host", f"{self.ADAPTATION_PROXY_IP}",
                "--proxy-port", f"{self.ADAPTATION_PROXY_PORT}",
                "--upstream-server-host", f"{self.WEB_SERVER_IP}",
                "--upstream-server-port", f"{self.WEB_SERVER_PORT}",
                "--adaptation-gain", f"{self.ADAPTATION_GAIN}",
                "--adaptation-bitrate-multiplier", f"{self.ADAPTATION_BITRATE_MULTIPLIER}"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.startOutputReaderThreads(self.miProxy)

    def startOutputReaderThreads(self, process):
        for stream in ["stdout", "stderr"]:
            threading.Thread(
                target=self.readStreamToOutputWindow,
                args=(process, stream),
                daemon=True
            ).start()

    def verifyInitializationSuccessful(self):
        # Wait a bit and make sure that both processes have started
        time.sleep(1)
        if self.webServer.poll() is not None:
            print("Web server failed to start")
            exit()
        if self.miProxy.poll() is not None:
            print("miProxy failed to start")
            exit()

    def handleUserInput(self):

        links = self.net.linksBetween(self.net["webServer"], self.net["router"])
        bwController = BandwidthController(next(iter(links)))

        prompt = CursesPrompt(self.promptWindow, "Enter bandwidth [kbps]: ")
        print(f"Current webServer<->router bandwidth limit: {bwController.getBandwidth()}")

        while True:
            self.refreshScreen()
            _, userInput = prompt.edit()
            try:
                newBandwidth = Quantity(float(userInput), "kilobits / second")
                bwController.setBandwidth(newBandwidth)
                print(f"Modified bandwidth to {newBandwidth}")
            except ValueError:
                pass
            print(f"Current webServer<->router bandwidth limit: {bwController.getBandwidth()}")
            prompt.clear()

if __name__ == "__main__":

    if not os.path.exists("../miProxy/miProxy"):
        print("Compile miProxy before testing!")
        sys.exit(1)

    if not os.path.exists("../nameserver/nameserver"):
        print("Compile nameserver before testing!")
        sys.exit(1)

    # Get the student's solutions
    copy("../miProxy/miProxy", "./miProxy")
    copy("../nameserver/nameserver", "./nameserver")

    # Start the topology
    stdscr = curses.initscr()
    Application(stdscr)
