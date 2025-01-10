from typing import NamedTuple

class NameserverLogFileEntry(NamedTuple):
    clientIP: str
    domainName: str
    answers: str

class NameserverLogFileParser:

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
        return NameserverLogFileEntry(
            clientIP=tokens[0],
            domainName=tokens[1],
            answers=tokens[2]
        )
