import io

class CursesWindowIO(io.StringIO):
    def __init__(self, window):
        super().__init__()
        self.window = window

    def write(self, s):
        super().write(s)
        self.window.addstr(s)
        self.window.refresh()
