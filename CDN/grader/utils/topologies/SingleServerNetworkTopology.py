#!/usr/bin/env python3.12

from mininet.topo import Topo
from mininet.node import Node
from mininet.link import TCLink
from ipaddress import IPv4Address
from utils.helper.subnetting import computeShortestPartitioningPrefix
from utils.helper.subnetting import computeLowestDifferentAddress

class LinuxRouter(Node):

    def config(self, **params):
        super(LinuxRouter, self).config(**params)
        self.cmd("sysctl net.ipv4.ip_forward=1")

    def terminate(self):
        self.cmd("sysctl net.ipv4.ip_forward=0")
        super(LinuxRouter, self).terminate()

class NetworkTopology(Topo):

    def __init__(self, routerIp, webServerIp, bitrateAdaptationProxyIp, clientIp,
                 *args, **kwargs):
        self.routerIp = IPv4Address(routerIp)
        self.webServerIp = IPv4Address(webServerIp)
        self.bitrateAdaptationProxyIp = IPv4Address(bitrateAdaptationProxyIp)
        self.clientIp = IPv4Address(clientIp)
        self.computeSubnetMask()
        self.computeInterfaceAddresses()
        super().__init__(*args, **kwargs)

    def build(self, **_opts):

        # Add router
        router = self.addNode("router", cls=LinuxRouter, ip=f"{self.routerIp}/{self.subnetMask}")

        # Add hosts
        webServer = self.addHost(
            "webServer",
            ip=f"{self.webServerIp}/{self.subnetMask}",
            defaultRoute=f"via {self.routerIp}"
        )
        bitrateAdaptationProxy = self.addHost(
            "bitrateAdaptationProxy",
            ip=f"{self.bitrateAdaptationProxyIp}/{self.subnetMask}",
            defaultRoute=f"via {self.bitrateAdaptationProxyInterfaceAddress}"
        )
        client = self.addHost(
            "client",
            ip=f"{self.clientIp}/{self.subnetMask}",
            defaultRoute=f"via {self.clientInterfaceAddress}",
            inNamespace=False
        )

        # Add links
        self.addLink(
            webServer, router, cls=TCLink, intfName1="webserv-router", intfName2="router-webserv",
            params2={"ip" : f"{self.routerIp}/{self.subnetMask}"}
        )
        self.addLink(
            bitrateAdaptationProxy, router, cls=TCLink, intfName1="proxy-router", intfName2="router-proxy",
            params2={"ip" : f"{self.bitrateAdaptationProxyInterfaceAddress}/{self.subnetMask}"}
        )
        self.addLink(
            client, router, cls=TCLink, intfName1="client-router", intfName2="router-client",
            params2={"ip" : f"{self.clientInterfaceAddress}/{self.subnetMask}"}
        )

    def computeSubnetMask(self):
        self.subnetMask = computeShortestPartitioningPrefix([
            self.routerIp, self.bitrateAdaptationProxyIp, self.clientIp
        ])

    def computeInterfaceAddresses(self):
        self.bitrateAdaptationProxyInterfaceAddress = computeLowestDifferentAddress(self.bitrateAdaptationProxyIp, self.subnetMask)
        self.clientInterfaceAddress = computeLowestDifferentAddress(self.clientIp, self.subnetMask)
