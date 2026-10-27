"""A module for tracking useful in-game information."""

import time
import cv2
import threading
import ctypes
import mss
import mss.windows
import numpy as np
from src.common import config, utils
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
gdi32 = ctypes.WinDLL('gdi32', use_last_error=True)
try:
    _hdesk = user32.OpenDesktopW('Default', 0, False, 0x10000000)
    if _hdesk:
        user32.SetThreadDesktop(_hdesk)
except Exception:
    pass
user32.SetProcessDPIAware()

PW_RENDERFULLCONTENT = 0x00000002


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ('biSize', wintypes.DWORD),
        ('biWidth', wintypes.LONG),
        ('biHeight', wintypes.LONG),
        ('biPlanes', wintypes.WORD),
        ('biBitCount', wintypes.WORD),
        ('biCompression', wintypes.DWORD),
        ('biSizeImage', wintypes.DWORD),
        ('biXPelsPerMeter', wintypes.LONG),
        ('biYPelsPerMeter', wintypes.LONG),
        ('biClrUsed', wintypes.DWORD),
        ('biClrImportant', wintypes.DWORD)
    ]


# The distance between the top of the minimap and the top of the screen
MINIMAP_TOP_BORDER = 5

# The thickness of the other three borders of the minimap
MINIMAP_BOTTOM_BORDER = 9

# Offset in pixels to adjust for windowed mode
WINDOWED_OFFSET_TOP = 36
WINDOWED_OFFSET_LEFT = 10

# The top-left and bottom-right corners of the minimap
MM_TL_TEMPLATE = cv2.imread('assets/minimap_tl_template.png', 0)
MM_BR_TEMPLATE = cv2.imread('assets/minimap_br_template.png', 0)

MMT_HEIGHT = max(MM_TL_TEMPLATE.shape[0], MM_BR_TEMPLATE.shape[0])
MMT_WIDTH = max(MM_TL_TEMPLATE.shape[1], MM_BR_TEMPLATE.shape[1])

# The player's symbol on the minimap
PLAYER_TEMPLATE = cv2.imread('assets/player_template.png', 0)
PT_HEIGHT, PT_WIDTH = PLAYER_TEMPLATE.shape


class Capture:
    """
    A class that tracks player position and various in-game events. It constantly updates
    the config module with information regarding these events. It also annotates and
    displays the minimap in a pop-up window.
    """

    def __init__(self):
        """Initializes this Capture object's main thread."""

        config.capture = self

        self.frame = None
        self.handle = 0
        self.minimap = {}
        self.minimap_ratio = 1
        self.minimap_sample = None
        self.sct = None
        self.window = {
            'left': 0,
            'top': 0,
            'width': 1366,
            'height': 768
        }

        self.ready = False
        self.calibrated = False
        self.thread = threading.Thread(target=self._main)
        self.thread.daemon = True

    def start(self):
        """Starts this Capture's thread."""

        print('\n[~] Started video capture')
        self.thread.start()

    def _main(self):
        """Constantly monitors the player's position and in-game events."""

        try:
            hdesk = user32.OpenDesktopW('Default', 0, False, 0x10000000)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass
        mss.windows.CAPTUREBLT = 0
        if hasattr(mss.windows, 'gdi'):
            mss.windows.gdi.CAPTUREBLT = 0
        self.ready = True
        while True:
            # Calibrate screen capture (supports multi-monitor negative coordinates)
            handle = user32.FindWindowW('MapleStoryClass', None) or user32.FindWindowW(None, 'MapleStory')
            if not handle:
                time.sleep(0.5)
                continue
            if user32.IsIconic(handle):
                user32.PostMessageW(handle, 0x0112, 0xF120, 0)  # WM_SYSCOMMAND, SC_RESTORE
                user32.ShowWindow(handle, 9)  # SW_RESTORE
                time.sleep(0.2)
                if user32.IsIconic(handle):
                    time.sleep(0.5)
                    continue
            self.handle = handle
            rect = wintypes.RECT()
            user32.GetWindowRect(handle, ctypes.pointer(rect))
            width = rect.right - rect.left
            height = rect.bottom - rect.top
            if width < 400 or height < 300:
                time.sleep(0.5)
                continue

            self.window['left'] = rect.left
            self.window['top'] = rect.top
            self.window['width'] = max(width, MMT_WIDTH)
            self.window['height'] = max(height, MMT_HEIGHT)

            # Calibrate by finding the top-left and bottom-right corners of the minimap
            with mss.mss() as self.sct:
                self.frame = self.screenshot()
            if self.frame is None:
                continue
            tl, _ = utils.single_match(self.frame, MM_TL_TEMPLATE)
            _, br = utils.single_match(self.frame, MM_BR_TEMPLATE)
            if tl[0] > 150 or tl[1] > 250 or br[0] - tl[0] <= MMT_WIDTH or br[1] - tl[1] <= MMT_HEIGHT:
                time.sleep(0.5)
                continue
            mm_tl = (
                tl[0] + MINIMAP_BOTTOM_BORDER,
                tl[1] + MINIMAP_TOP_BORDER
            )
            mm_br = (
                max(mm_tl[0] + PT_WIDTH, br[0] - MINIMAP_BOTTOM_BORDER),
                max(mm_tl[1] + PT_HEIGHT, br[1] - MINIMAP_BOTTOM_BORDER)
            )
            self.minimap_ratio = (mm_br[0] - mm_tl[0]) / (mm_br[1] - mm_tl[1])
            self.minimap_sample = self.frame[mm_tl[1]:mm_br[1], mm_tl[0]:mm_br[0]]
            self.calibrated = True

            with mss.mss() as self.sct:
                while True:
                    if not self.calibrated or not user32.IsWindow(handle):
                        self.calibrated = False
                        break

                    # Take screenshot
                    self.frame = self.screenshot()
                    if self.frame is None:
                        continue

                    # Crop the frame to only show the minimap
                    minimap = self.frame[mm_tl[1]:mm_br[1], mm_tl[0]:mm_br[0]]

                    # Determine the player's position
                    player = utils.multi_match(minimap, PLAYER_TEMPLATE, threshold=0.8)
                    if player:
                        config.player_pos = utils.convert_to_relative(player[0], minimap)

                    # Package display information to be polled by GUI
                    self.minimap = {
                        'minimap': minimap,
                        'rune_active': config.bot.rune_active,
                        'rune_pos': config.bot.rune_pos,
                        'path': config.path,
                        'player_pos': config.player_pos
                    }

                    if not self.ready:
                        self.ready = True
                    time.sleep(0.001)

    def _print_window(self):
        """Captures the target window in the background via PrintWindow + PW_RENDERFULLCONTENT."""

        if not self.handle or not user32.IsWindow(self.handle) or user32.IsIconic(self.handle):
            return None
        w = self.window['width']
        h = self.window['height']
        if w <= 0 or h <= 0:
            return None
        hwndDC = user32.GetWindowDC(self.handle)
        if not hwndDC:
            return None
        mfcDC = gdi32.CreateCompatibleDC(hwndDC)
        saveBitMap = gdi32.CreateCompatibleBitmap(hwndDC, w, h)
        gdi32.SelectObject(mfcDC, saveBitMap)
        try:
            res = user32.PrintWindow(self.handle, mfcDC, PW_RENDERFULLCONTENT)
            if not res:
                return None
            bmi = BITMAPINFOHEADER()
            bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
            bmi.biWidth = w
            bmi.biHeight = -h
            bmi.biPlanes = 1
            bmi.biBitCount = 32
            bmi.biCompression = 0
            buf = ctypes.create_string_buffer(w * h * 4)
            gdi32.GetDIBits(mfcDC, saveBitMap, 0, h, buf, ctypes.byref(bmi), 0)
            img = np.frombuffer(buf, dtype=np.uint8).reshape((h, w, 4)).copy()
            if img[:, :, :3].max() == 0:
                return None
            return img
        finally:
            gdi32.DeleteObject(saveBitMap)
            gdi32.DeleteDC(mfcDC)
            user32.ReleaseDC(self.handle, hwndDC)

    def screenshot(self, delay=1):
        try:
            bg_img = self._print_window()
            if bg_img is not None:
                return bg_img
            return np.array(self.sct.grab(self.window))
        except mss.exception.ScreenShotError:
            print(f'\n[!] Error while taking screenshot, retrying in {delay} second'
                  + ('s' if delay != 1 else ''))
            time.sleep(delay)
