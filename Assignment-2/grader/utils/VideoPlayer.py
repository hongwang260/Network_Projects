import logging

from pint import Quantity

class VideoPlayer:

    HTML_VIDEO_ELEMENT_ID = "player"
    TIMEOUT_REQ_DURATION_MULTIPLIER = 5

    def __init__(self, browserContext, hlsPlayerUrl):
        self.page = browserContext.new_page()
        self.page.on("console", lambda msg: logging.info(msg.text))
        self.page.goto(hlsPlayerUrl)

    def getVideoPosition(self):
        position = self.page.evaluate(f"document.getElementById('{self.HTML_VIDEO_ELEMENT_ID}').currentTime")
        return Quantity(position, "seconds")

    def playVideo(self):
        self.page.evaluate(f"document.getElementById('{self.HTML_VIDEO_ELEMENT_ID}').play()")

    def pauseVideo(self):
        self.page.evaluate(f"document.getElementById('{self.HTML_VIDEO_ELEMENT_ID}').pause()")

    def playVideoUntil(self, targetTime):
        currentTime = self.getVideoPosition()
        duration = targetTime - currentTime
        self.playVideo()
        self.page.wait_for_function(
            f"document.getElementById('{self.HTML_VIDEO_ELEMENT_ID}').currentTime >= {targetTime.to("seconds").magnitude}",
            timeout=(duration.to("milliseconds").magnitude * self.TIMEOUT_REQ_DURATION_MULTIPLIER)
        )
        self.pauseVideo()

    def playVideoFor(self, duration):
        currentTime = self.getVideoPosition()
        targetTime = currentTime + duration
        self.playVideo()
        self.page.wait_for_function(
            f"document.getElementById('{self.HTML_VIDEO_ELEMENT_ID}').currentTime >= {targetTime.to("seconds").magnitude}",
            timeout=(duration.to("milliseconds").magnitude * self.TIMEOUT_REQ_DURATION_MULTIPLIER)
        )
        self.pauseVideo()

    def close(self):
        self.page.close()
