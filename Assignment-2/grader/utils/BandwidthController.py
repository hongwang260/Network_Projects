
from mininet.link import TCLink
from pint import Quantity

class BandwidthController:

    MAX_BW = Quantity(1000, "megabit / second")

    def __init__(self, link: TCLink):
        self.link = link

    def getBandwidth(self):
        return self._getCurrentBandwidthLimit()

    def setBandwidth(self, newBandwidth):
        if newBandwidth <= 0 or newBandwidth > self.MAX_BW:
            raise ValueError
        self._setNewBandwidthLimit(newBandwidth)
        assert self._getCurrentBandwidthLimit() == newBandwidth, "Sanity check: bandwidth set correctly"

    def _getCurrentBandwidthLimit(self):
        def getInterfaceBandwidthLimit(interface):
            result = interface.cmd(f"tc class show dev {interface.name}")
            for line in result.split("\n"):
                if "class hfsc" in line and "m2" in line:
                    rate = line.split("m2")[1].split()[0]
                    rate = rate.replace("Gbit", "gigabit / second")
                    rate = rate.replace("Mbit", "megabit / second")
                    rate = rate.replace("Kbit", "kilobit / second")
                    return Quantity(rate)
            return None
        intf1Bw = getInterfaceBandwidthLimit(self.link.intf1)
        intf2Bw = getInterfaceBandwidthLimit(self.link.intf2)
        assert intf2Bw == intf1Bw, "Sanity check: link bandwidth should be symmetric"
        return intf1Bw

    def _setNewBandwidthLimit(self, newBandwidth):
        self.link.intf1.config(bw=newBandwidth.to("megabits / second").magnitude, use_hfsc=True)
        self.link.intf2.config(bw=newBandwidth.to("megabits / second").magnitude, use_hfsc=True)
