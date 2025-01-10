from typing import NamedTuple
from pint import Quantity

class ProxyLogFileEntry(NamedTuple):
    browserIP: str
    segmentName: str
    adapatationProxyIP: str
    segmentTransferTime: Quantity
    segmentTransferThroughput: Quantity
    averageConnectionThroughput: Quantity
    bitrateChosen: Quantity

class ProxyLogFileParser:

    def __init__(self, logFilePath):
        self.logFilePath = logFilePath
        self.lastParsedEntryIdx = -1

    def parseNewEntries(self):
        logEntries = []
        with open(self.logFilePath, "r") as logFile:
            for idx, line in enumerate(logFile):
                if idx > self.lastParsedEntryIdx:
                    entry = self._parseEntry(line)
                    logEntries.append(entry)
                    self.lastParsedEntryIdx = idx
        return logEntries

    def _parseEntry(self, line):
        tokens = line.rstrip("\n").split(" ")
        return ProxyLogFileEntry(
            browserIP=tokens[0],
            segmentName=tokens[1],
            adapatationProxyIP=tokens[2],
            segmentTransferTime=Quantity(float(tokens[3]), "seconds"),
            segmentTransferThroughput=Quantity(float(tokens[4]), "kilobits / second"),
            averageConnectionThroughput=Quantity(float(tokens[5]), "kilobits / second"),
            bitrateChosen=Quantity(float(tokens[6]), "kilobits / second")
        )
