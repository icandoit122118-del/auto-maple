"""The central program that ties all the modules together."""

import ctypes
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Disable Windows Console QuickEdit mode and attach to Default desktop
try:
    user32 = ctypes.windll.user32
    hdesk = user32.OpenDesktopW('Default', 0, False, 0x10000000)
    if hdesk:
        user32.SetThreadDesktop(hdesk)
    kernel32 = ctypes.windll.kernel32
    h_stdin = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(h_stdin, ctypes.byref(mode)):
        mode.value &= ~0x0040  # ~ENABLE_QUICK_EDIT_MODE
        mode.value |= 0x0080   # ENABLE_EXTENDED_FLAGS
        kernel32.SetConsoleMode(h_stdin, mode.value)
except Exception:
    pass

# Self-elevate to Administrator if needed so PrintWindow and PostMessageW bypass UIPI
try:
    if not ctypes.windll.shell32.IsUserAnAdmin() and '--no-elevate' not in sys.argv and '--elevated' not in sys.argv:
        print('[~] Elevating Auto Maple to Administrator for PrintWindow / PostMessageW...')
        ctypes.windll.shell32.ShellExecuteW(
            None,
            'runas',
            sys.executable,
            ' '.join([f'"{arg}"' for arg in sys.argv] + ['--no-elevate']),
            PROJECT_ROOT,
            1
        )
        sys.exit(0)
except Exception:
    pass

from src.modules.bot import Bot
from src.modules.capture import Capture
from src.modules.notifier import Notifier
from src.modules.listener import Listener
from src.modules.gui import GUI


bot = Bot()
capture = Capture()
notifier = Notifier()
listener = Listener()

bot.start()
while not bot.ready:
    time.sleep(0.01)

capture.start()
while not capture.ready:
    time.sleep(0.01)

notifier.start()
while not notifier.ready:
    time.sleep(0.01)

listener.start()
while not listener.ready:
    time.sleep(0.01)

print('\n[~] Successfully initialized Auto Maple')

gui = GUI()
gui.start()
