#!/usr/bin/env python3.12

import time
import sys
import curses
import subprocess
import threading
import tempfile
import os

from utils.topologies.MultipleServersNetworkTopology import NetworkTopology
from utils.BandwidthController import BandwidthController
from utils.CursesWindowIO import CursesWindowIO
from utils.CursesPrompt import CursesPrompt, SpecialCodes

from mininet.net import Mininet
from mininet.node import OVSController
from pint import Quantity
from shutil import copy

class Application:

    DOMAIN_NAME = "video.cdn.assignment2.test"

    ROUTER_IP = "10.0.1.1"

    WEB_SERVER1_IP = "10.0.1.100"
    WEB_SERVER1_PORT = 8000
    WEB_SERVER1_CONTENT_PATH = "www"

    WEB_SERVER2_IP = "10.0.2.100"
    WEB_SERVER2_PORT = 8000
    WEB_SERVER2_CONTENT_PATH = "www"

    NAME_SERVER_IP = "10.0.3.100"
    NAME_SERVER_PORT = 53
    NAME_SERVER_ROUND_ROBIN_IP_LIST = "servers.txt"

    ADAPTATION_PROXY1_IP = "10.0.4.100"
    ADAPTATION_PROXY1_PORT = 9000

    ADAPTATION_PROXY2_IP = "10.0.5.100"
    ADAPTATION_PROXY2_PORT = 9000

    ADAPTATION_GAIN = 0.35
    ADAPTATION_BITRATE_MULTIPLIER = 1.5

    CLIENT_IP = "10.0.6.100"

    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.initializeScreen()
        self.setupWindows()
        self.setupIORedirection()
        self.startMininet()
        self.startWebServers()
        self.startNameserver()
        time.sleep(2) # Make sure that the name server is up
        self.startBitrateAdaptationProxies()
        self.verifyInitializationSuccessful()
        try:
            self.handleUserInput()
        except KeyboardInterrupt:
            print("\nCTRL+C pressed. Shutting down...")
        self.prompt1Window.clear()
        self.prompt1Window.refresh()
        self.prompt2Window.clear()
        self.prompt2Window.refresh()
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
        prompt1WindowPosition = (self.height - 2 * promptWindowHeight, 0)
        prompt2WindowPosition = (self.height - 1 * promptWindowHeight, 0)
        outputWindowHeight = self.height - 2 * promptWindowHeight - spacingBetweenWindows
        outputWindowWidth = self.width
        outputWindowPosition = (0, 0)
        # Create prompt 1 window
        self.prompt1Window = self.stdscr.subwin(promptWindowHeight, promptWindowWidth, *prompt1WindowPosition)
        # Create prompt 2 window
        self.prompt2Window = self.stdscr.subwin(promptWindowHeight, promptWindowWidth, *prompt2WindowPosition)
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
                self.prompt1Window.refresh()  # Refresh the prompt window to keep the cursor at the bottom

    def setupIORedirection(self):
        # Redirect stdout/stderr to output window
        sys.stdout = CursesWindowIO(self.outputWindow)
        sys.stderr = CursesWindowIO(self.outputWindow)

    def startMininet(self):
        self.topology = NetworkTopology(
            routerIp=self.ROUTER_IP,
            webServer1Ip=self.WEB_SERVER1_IP,
            webServer2Ip=self.WEB_SERVER2_IP,
            nameServerIp=self.NAME_SERVER_IP,
            bitrateAdaptationProxy1Ip=self.ADAPTATION_PROXY1_IP,
            bitrateAdaptationProxy2Ip=self.ADAPTATION_PROXY2_IP,
            clientIp=self.CLIENT_IP
        )
        self.net = Mininet(topo=self.topology, waitConnected=True)
        self.net.addController(name="controller", controller=OVSController)
        self.net.start()

    def startWebServers(self):
        self.webServer1 = self.net["webServer1"].popen([
                "./webserver.py",
                "--host", f"{self.WEB_SERVER1_IP}",
                "--port", f"{self.WEB_SERVER1_PORT}",
                "--content-path", f"{self.WEB_SERVER1_CONTENT_PATH}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.startOutputReaderThreads(self.webServer1)
        self.webServer2 = self.net["webServer2"].popen([
                "./webserver.py",
                "--host", f"{self.WEB_SERVER2_IP}",
                "--port", f"{self.WEB_SERVER2_PORT}",
                "--content-path", f"{self.WEB_SERVER2_CONTENT_PATH}",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.startOutputReaderThreads(self.webServer2)

    def startNameserver(self):
        self.ipListFile = tempfile.NamedTemporaryFile(mode="w", delete_on_close=True)
        self.ipListFile.writelines(ipAddress + "\n" for ipAddress in [self.WEB_SERVER1_IP, self.WEB_SERVER2_IP])
        self.ipListFile.flush()
        self.nameServer = self.net["nameServer"].popen([
                "./nameserver",
                "--ip", f"{self.NAME_SERVER_IP}",
                "--port", f"{self.NAME_SERVER_PORT}",
                "--domain", f"{self.DOMAIN_NAME}",
                "--round-robin-ip-list-file-path", f"{self.ipListFile.name}"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.startOutputReaderThreads(self.nameServer)

    def startBitrateAdaptationProxies(self):
        self.miProxy1 = self.net["bitrateAdaptationProxy1"].popen([
                "./miProxy",
                "--proxy-host", f"{self.ADAPTATION_PROXY1_IP}",
                "--proxy-port", f"{self.ADAPTATION_PROXY1_PORT}",
                "--upstream-server-host", f"{self.DOMAIN_NAME}",
                "--upstream-server-port", f"{self.WEB_SERVER1_PORT}",
                "--adaptation-gain", f"{self.ADAPTATION_GAIN}",
                "--adaptation-bitrate-multiplier", f"{self.ADAPTATION_BITRATE_MULTIPLIER}",
                "--nameserver-ip", f"{self.NAME_SERVER_IP}",
                "--nameserver-port", f"{self.NAME_SERVER_PORT}"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.startOutputReaderThreads(self.miProxy1)
        self.miProxy2 = self.net["bitrateAdaptationProxy2"].popen([
                "./miProxy",
                "--proxy-host", f"{self.ADAPTATION_PROXY2_IP}",
                "--proxy-port", f"{self.ADAPTATION_PROXY2_PORT}",
                "--upstream-server-host", f"{self.DOMAIN_NAME}",
                "--upstream-server-port", f"{self.WEB_SERVER2_PORT}",
                "--adaptation-gain", f"{self.ADAPTATION_GAIN}",
                "--adaptation-bitrate-multiplier", f"{self.ADAPTATION_BITRATE_MULTIPLIER}",
                "--nameserver-ip", f"{self.NAME_SERVER_IP}",
                "--nameserver-port", f"{self.NAME_SERVER_PORT}"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        self.startOutputReaderThreads(self.miProxy2)

    def startOutputReaderThreads(self, process):
        for stream in ["stdout", "stderr"]:
            threading.Thread(
                target=self.readStreamToOutputWindow,
                args=(process, stream),
                daemon=True
            ).start()

    def verifyInitializationSuccessful(self):
        # Wait a bit and make sure that all processes have started
        time.sleep(1)
        if self.webServer1.poll() is not None or self.webServer2.poll() is not None:
            print("Web servers failed to start")
            exit()
        if self.nameServer.poll() is not None:
            print("Nameserver failed to start")
            self.webServer1.terminate()
            self.webServer1.wait()
            self.webServer2.terminate()
            self.webServer2.wait()
            exit()
        if self.miProxy1.poll() is not None or self.miProxy2.poll() is not None:
            print("miProxy failed to start")
            self.webServer1.terminate()
            self.webServer1.wait()
            self.webServer2.terminate()
            self.webServer2.wait()
            self.nameServer.terminate()
            exit()

    def handleUserInput(self):

        webServer1Links = self.net.linksBetween(self.net["webServer1"], self.net["router"])
        webServer2Links = self.net.linksBetween(self.net["webServer2"], self.net["router"])
        bwController1 = BandwidthController(next(iter(webServer1Links)))
        bwController2 = BandwidthController(next(iter(webServer2Links)))

        prompt1 = CursesPrompt(self.prompt1Window, "Enter bandwidth limit for web server 1 [kbps]: ")
        prompt2 = CursesPrompt(self.prompt2Window, "Enter bandwidth limit for web server 2 [kbps]: ")

        # Main loop to handle user input
        currentPrompt = prompt1
        print(f"Current webServer1<->router bandwidth limit: {bwController1.getBandwidth()}")
        print(f"Current webServer2<->router bandwidth limit: {bwController2.getBandwidth()}")

        while True:

            self.refreshScreen()
            exitKey, userInput = currentPrompt.edit()

            match exitKey:

                case curses.KEY_ENTER | SpecialCodes.CARRIAGE_RET | SpecialCodes.NEWLINE:
                    try:
                        newBandwidth = Quantity(float(userInput), "kilobits / second")
                        if currentPrompt == prompt1:
                            bwController1.setBandwidth(newBandwidth)
                            print(f"Modified bandwidth to web server 1 to {newBandwidth}")
                        else:
                            bwController2.setBandwidth(newBandwidth)
                            print(f"Modified bandwidth to web server 2 to {newBandwidth}")
                    except ValueError:
                        pass

                    print(f"Current webServer1<->router bandwidth limit: {bwController1.getBandwidth()}")
                    print(f"Current webServer2<->router bandwidth limit: {bwController2.getBandwidth()}")

                case curses.KEY_UP | curses.KEY_DOWN:
                    if currentPrompt == prompt1:
                        currentPrompt = prompt2
                    else:
                        currentPrompt = prompt1

            currentPrompt.clear()

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
