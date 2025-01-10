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

    def __init__(self, routerIp, webServer1Ip, webServer2Ip, nameServerIp,
                 bitrateAdaptationProxy1Ip, bitrateAdaptationProxy2Ip, clientIp,
                 *args, **kwargs):
        self.routerIp = IPv4Address(routerIp)
        self.webServer1Ip = IPv4Address(webServer1Ip)
        self.webServer2Ip = IPv4Address(webServer2Ip)
        self.nameServerIp = IPv4Address(nameServerIp)
        self.bitrateAdaptationProxy1Ip = IPv4Address(bitrateAdaptationProxy1Ip)
        self.bitrateAdaptationProxy2Ip = IPv4Address(bitrateAdaptationProxy2Ip)
        self.clientIp = IPv4Address(clientIp)
        self.computeSubnetMask()
        self.computeInterfaceAddresses()
        super().__init__(*args, **kwargs)

    def build(self, **_opts):

        # Add router
        router = self.addNode("router", cls=LinuxRouter, ip=f"{self.routerIp}/{self.subnetMask}")

        # Add hosts
        webServer1 = self.addHost(
            "webServer1",
            ip=f"{self.webServer1Ip}/{self.subnetMask}",
            defaultRoute=f"via {self.routerIp}"
        )
        webServer2 = self.addHost(
            "webServer2",
            ip=f"{self.webServer2Ip}/{self.subnetMask}",
            defaultRoute=f"via {self.webServer2InterfaceAddress}"
        )
        nameServer = self.addHost(
            "nameServer",
            ip=f"{self.nameServerIp}/{self.subnetMask}",
            defaultRoute=f"via {self.nameServerInterfaceAddress}"
        )
        bitrateAdaptationProxy1 = self.addHost(
            "bitrateAdaptationProxy1",
            ip=f"{self.bitrateAdaptationProxy1Ip}/{self.subnetMask}",
            defaultRoute=f"via {self.bitrateAdaptationProxy1InterfaceAddress}"
        )
        bitrateAdaptationProxy2 = self.addHost(
            "bitrateAdaptationProxy2",
            ip=f"{self.bitrateAdaptationProxy2Ip}/{self.subnetMask}",
            defaultRoute=f"via {self.bitrateAdaptationProxy2InterfaceAddress}"
        )
        client = self.addHost(
            "client",
            ip=f"{self.clientIp}/{self.subnetMask}",
            defaultRoute=f"via {self.clientInterfaceAddress}",
            inNamespace=False
        )

        # Add links
        self.addLink(
            webServer1, router, cls=TCLink, intfName1="webserv1-router", intfName2="router-webserv1",
            params2={"ip" : f"{self.routerIp}/{self.subnetMask}"}
        )
        self.addLink(
            webServer2, router, cls=TCLink, intfName1="webserv2-router", intfName2="router-webserv2",
            params2={"ip" : f"{self.webServer2InterfaceAddress}/{self.subnetMask}"}
        )
        self.addLink(
            nameServer, router, cls=TCLink, intfName1="nameserv-router", intfName2="router-nameserv",
            params2={"ip" : f"{self.nameServerInterfaceAddress}/{self.subnetMask}"}
        )
        self.addLink(
            bitrateAdaptationProxy1, router, cls=TCLink, intfName1="proxy1-router", intfName2="router-proxy1",
            params2={"ip" : f"{self.bitrateAdaptationProxy1InterfaceAddress}/{self.subnetMask}"}
        )
        self.addLink(
            bitrateAdaptationProxy2, router, cls=TCLink, intfName1="proxy2-router", intfName2="router-proxy2",
            params2={"ip" : f"{self.bitrateAdaptationProxy2InterfaceAddress}/{self.subnetMask}"}
        )
        self.addLink(
            client, router, cls=TCLink, intfName1="client-router", intfName2="router-client",
            params2={"ip" : f"{self.clientInterfaceAddress}/{self.subnetMask}"}
        )

    def computeSubnetMask(self):
        self.subnetMask = computeShortestPartitioningPrefix([
            self.routerIp, self.webServer2Ip, self.nameServerIp, self.bitrateAdaptationProxy1Ip,
            self.bitrateAdaptationProxy2Ip, self.clientIp
        ])

    def computeInterfaceAddresses(self):
        self.webServer2InterfaceAddress = computeLowestDifferentAddress(self.webServer2Ip, self.subnetMask)
        self.nameServerInterfaceAddress = computeLowestDifferentAddress(self.nameServerIp, self.subnetMask)
        self.bitrateAdaptationProxy1InterfaceAddress = computeLowestDifferentAddress(self.bitrateAdaptationProxy1Ip, self.subnetMask)
        self.bitrateAdaptationProxy2InterfaceAddress = computeLowestDifferentAddress(self.bitrateAdaptationProxy2Ip, self.subnetMask)
        self.clientInterfaceAddress = computeLowestDifferentAddress(self.clientIp, self.subnetMask)
