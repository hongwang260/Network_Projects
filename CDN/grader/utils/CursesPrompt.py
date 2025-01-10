import curses
import contextlib

class SpecialCodes:
    CARRIAGE_RET = ord("\r")
    NEWLINE = ord("\n")

class CursesPrompt:

    def __init__(self, window, promptMessage):
        self.window = window
        self.promptMessage = promptMessage
        self.printPromptMessage()
        self.cursorPosition = len(promptMessage)
        self.content = []

    def printPromptMessage(self):
        self.window.refresh()
        self.window.addstr(0, 0, self.promptMessage)
        self.window.refresh()

    def appendCharacter(self, character):
        _, windowWdith = self.window.getmaxyx()
        if self.cursorPosition == windowWdith:
            return # Prevent writing off the edge
        self.window.addch(0, self.cursorPosition, character)
        self.content.insert(self.cursorPosition, chr(character))
        self.cursorPosition += 1

    def deleteLastCharacter(self):
        if self.cursorPosition <= len(self.promptMessage):
            return # Prevent writing over the prompt message
        self.cursorPosition -= 1
        self.window.delch(0, self.cursorPosition)
        if self.content:
            self.content.pop()

    def moveCursorLeft(self):
        if self.cursorPosition == len(self.promptMessage):
            return # Prevent moving cursor over the prompt message
        self.cursorPosition -= 1

    def moveCursorRight(self):
        _, windowWdith = self.window.getmaxyx()
        if self.cursorPosition == windowWdith:
            return # Prevent writing off the edge
        self.cursorPosition += 1

    def getText(self):
        return "".join(self.content)

    def clearText(self):
        self.content = []
        self.cursorPosition = len(self.promptMessage)

    def edit(self):
        text = self.promptMessage + "".join(self.content)
        self.window.refresh()
        self.window.addstr(0, 0, text)
        with self.editMode():
            while True:
                key = self.window.getch()
                match key:
                    case curses.KEY_BACKSPACE:
                        self.deleteLastCharacter()
                    case curses.KEY_LEFT:
                        self.moveCursorLeft()
                    case curses.KEY_RIGHT:
                        self.moveCursorRight()
                    case curses.KEY_ENTER | SpecialCodes.CARRIAGE_RET | SpecialCodes.NEWLINE:
                        userInput = self.getText()
                        self.clearText()
                        break
                    case curses.KEY_UP | curses.KEY_DOWN:
                        userInput = self.getText()
                        break
                    case _:
                        self.appendCharacter(key)
                self.window.move(0, self.cursorPosition)
                self.window.refresh()
        return key, userInput

    def clear(self):
        self.window.clear()
        self.window.refresh()

    @contextlib.contextmanager
    def editMode(self):
        try:
            curses.noecho()
            self.window.keypad(True)
            yield
        finally:
            self.window.keypad(False)
            curses.echo()
