from ipaddress import IPv4Network

def computeShortestPartitioningPrefix(ipList):
    """
        Compute the shortest prefix such that every ip address in ipList
        is in a different subnet
    """
    prefixLength = 32
    # Start with the smallest possible prefix length
    for prefixLength in range(0, 32):
        # Create a set to track unique subnets
        subnets = set()
        for ip in ipList:
            # Create a network with the current prefix length
            network = IPv4Network(f"{ip}/{prefixLength}", strict=False)
            subnets.add(network.network_address)
        # If the number of unique networks is equal to the number of IP addresses,
        # it means that all IPs are in separate subnets
        if len(subnets) == len(ipList):
            break
    return prefixLength

def computeLowestDifferentAddress(referenceIp, subnetMask):
    """
        Given an ip address and a subnet mask, compute the lowest ip address
        in the subnet that is different from the given ip address
    """
    subnet = IPv4Network((referenceIp, subnetMask), strict=False)
    for ip in subnet.hosts():
        if ip != referenceIp:
            return ip
