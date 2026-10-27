"""A module for simulating low-level keyboard and mouse key presses (PostMessageW + Win11 Focus Control + SendInput)."""

import ctypes
import time
import win32con
import win32api
from src.common import config, utils
from ctypes import wintypes
from random import random


user32 = ctypes.WinDLL('user32', use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
INPUT_HARDWARE = 2

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
MK_LBUTTON = 0x0001
MK_RBUTTON = 0x0002

MAPVK_VK_TO_VSC = 0
VK_MENU = 0x12

EXTENDED_KEYS = {
    'left', 'up', 'right', 'down',
    'insert', 'delete', 'home', 'end', 'page up', 'page down'
}

# https://docs.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes?redirectedfrom=MSDN
KEY_MAP = {
    'left': 0x25,   # Arrow keys
    'up': 0x26,
    'right': 0x27,
    'down': 0x28,

    'backspace': 0x08,      # Special keys
    'tab': 0x09,
    'enter': 0x0D,
    'shift': 0x10,
    'ctrl': 0x11,
    'alt': 0x12,
    'caps lock': 0x14,
    'esc': 0x1B,
    'space': 0x20,
    'page up': 0x21,
    'page down': 0x22,
    'end': 0x23,
    'home': 0x24,
    'insert': 0x2D,
    'delete': 0x2E,

    '0': 0x30,      # Numbers
    '1': 0x31,
    '2': 0x32,
    '3': 0x33,
    '4': 0x34,
    '5': 0x35,
    '6': 0x36,
    '7': 0x37,
    '8': 0x38,
    '9': 0x39,

    'a': 0x41,      # Letters
    'b': 0x42,
    'c': 0x43,
    'd': 0x44,
    'e': 0x45,
    'f': 0x46,
    'g': 0x47,
    'h': 0x48,
    'i': 0x49,
    'j': 0x4A,
    'k': 0x4B,
    'l': 0x4C,
    'm': 0x4D,
    'n': 0x4E,
    'o': 0x4F,
    'p': 0x50,
    'q': 0x51,
    'r': 0x52,
    's': 0x53,
    't': 0x54,
    'u': 0x55,
    'v': 0x56,
    'w': 0x57,
    'x': 0x58,
    'y': 0x59,
    'z': 0x5A,

    'f1': 0x70,     # Functional keys
    'f2': 0x71,
    'f3': 0x72,
    'f4': 0x73,
    'f5': 0x74,
    'f6': 0x75,
    'f7': 0x76,
    'f8': 0x77,
    'f9': 0x78,
    'f10': 0x79,
    'f11': 0x7A,
    'f12': 0x7B,
    'num lock': 0x90,
    'scroll lock': 0x91,

    ';': 0xBA,      # Special characters
    '=': 0xBB,
    ',': 0xBC,
    '-': 0xBD,
    '.': 0xBE,
    '/': 0xBF,
    '`': 0xC0,
    '[': 0xDB,
    '\\': 0xDC,
    ']': 0xDD,
    "'": 0xDE
}


#################################
#     C Struct Definitions      #
#################################
wintypes.ULONG_PTR = wintypes.WPARAM


class KeyboardInput(ctypes.Structure):
    _fields_ = (('wVk', wintypes.WORD),
                ('wScan', wintypes.WORD),
                ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD),
                ('dwExtraInfo', wintypes.ULONG_PTR))

    def __init__(self, *args, **kwargs):
        super(KeyboardInput, self).__init__(*args, **kwargs)
        if not self.dwFlags & KEYEVENTF_UNICODE:
            self.wScan = user32.MapVirtualKeyExW(self.wVk, MAPVK_VK_TO_VSC, 0)


class MouseInput(ctypes.Structure):
    _fields_ = (('dx', wintypes.LONG),
                ('dy', wintypes.LONG),
                ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD),
                ('dwExtraInfo', wintypes.ULONG_PTR))


class HardwareInput(ctypes.Structure):
    _fields_ = (('uMsg', wintypes.DWORD),
                ('wParamL', wintypes.WORD),
                ('wParamH', wintypes.WORD))


class Input(ctypes.Structure):
    class _Input(ctypes.Union):
        _fields_ = (('ki', KeyboardInput),
                    ('mi', MouseInput),
                    ('hi', HardwareInput))

    _anonymous_ = ('_input',)
    _fields_ = (('type', wintypes.DWORD),
                ('_input', _Input))


LPINPUT = ctypes.POINTER(Input)


def err_check(result, _, args):
    if result == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    else:
        return args


user32.SendInput.errcheck = err_check
user32.SendInput.argtypes = (wintypes.UINT, LPINPUT, ctypes.c_int)

_saved_prev_hwnd = 0


def _get_target_hwnd():
    if config.capture is not None and getattr(config.capture, 'handle', 0):
        return config.capture.handle
    return user32.FindWindowW('MapleStoryClass', None) or user32.FindWindowW(None, 'MapleStory')


def _force_activate_window(hwnd):
    """Unlocks Windows 11 ForegroundLockTimeout and brings HWND to the active foreground."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    if user32.IsIconic(hwnd):
        user32.PostMessageW(hwnd, 0x0112, 0xF120, 0)  # WM_SYSCOMMAND, SC_RESTORE
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        time.sleep(0.02)
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return True
    user32.keybd_event(VK_MENU, 0, 0, 0)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SwitchToThisWindow(hwnd, True)
    finally:
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    for _ in range(10):
        if user32.GetForegroundWindow() == hwnd:
            return True
        time.sleep(0.005)
    return user32.GetForegroundWindow() == hwnd


def _ensure_foreground(hwnd):
    """Acquires foreground focus on MapleStory according to config.bg_input_mode."""
    global _saved_prev_hwnd
    mode = getattr(config, 'bg_input_mode', 'auto_focus')
    if mode == 'postmessage_only':
        return user32.GetForegroundWindow() == hwnd
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    fg = user32.GetForegroundWindow()
    if fg != hwnd and fg != 0:
        _saved_prev_hwnd = fg
    return _force_activate_window(hwnd)


def _restore_previous_foreground(target_hwnd):
    """Restores focus to the previous window when config.bg_input_mode == 'focus_restore'."""
    global _saved_prev_hwnd
    mode = getattr(config, 'bg_input_mode', 'auto_focus')
    if mode == 'focus_restore' and _saved_prev_hwnd and _saved_prev_hwnd != target_hwnd:
        if user32.IsWindow(_saved_prev_hwnd):
            _force_activate_window(_saved_prev_hwnd)
        _saved_prev_hwnd = 0


def _build_key_lparam(key, vk, is_up=False):
    scan = user32.MapVirtualKeyExW(vk, MAPVK_VK_TO_VSC, 0)
    lparam = 1 | (scan << 16)
    if key in EXTENDED_KEYS:
        lparam |= (1 << 24)
    if is_up:
        lparam |= (1 << 30) | (1 << 31)
    return lparam


#################################
#           Functions           #
#################################
@utils.run_if_enabled
def key_down(key):
    """
    Simulates a key-down action via PostMessageW and hardware-scancode SendInput.
    Can be cancelled by Bot.toggle_enabled.
    :param key:     The key to press.
    :return:        None
    """

    key = key.lower()
    if key not in KEY_MAP.keys():
        print(f"Invalid keyboard input: '{key}'.")
    else:
        vk = KEY_MAP[key]
        hwnd = _get_target_hwnd()
        if hwnd:
            user32.PostMessageW(hwnd, WM_KEYDOWN, vk, _build_key_lparam(key, vk, is_up=False))
            _ensure_foreground(hwnd)
        if not hwnd or user32.GetForegroundWindow() == hwnd:
            flags = KEYEVENTF_EXTENDEDKEY if key in EXTENDED_KEYS else 0
            x = Input(type=INPUT_KEYBOARD, ki=KeyboardInput(wVk=vk, dwFlags=flags))
            user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))


def key_up(key):
    """
    Simulates a key-up action via PostMessageW and hardware-scancode SendInput.
    Cannot be cancelled by Bot.toggle_enabled.
    This is to ensure no keys are left in the 'down' state when the program pauses.
    :param key:     The key to press.
    :return:        None
    """

    key = key.lower()
    if key not in KEY_MAP.keys():
        print(f"Invalid keyboard input: '{key}'.")
    else:
        vk = KEY_MAP[key]
        hwnd = _get_target_hwnd()
        if hwnd:
            user32.PostMessageW(hwnd, WM_KEYUP, vk, _build_key_lparam(key, vk, is_up=True))
        if not hwnd or user32.GetForegroundWindow() == hwnd:
            flags = KEYEVENTF_KEYUP | (KEYEVENTF_EXTENDEDKEY if key in EXTENDED_KEYS else 0)
            x = Input(type=INPUT_KEYBOARD, ki=KeyboardInput(wVk=vk, dwFlags=flags))
            user32.SendInput(1, ctypes.byref(x), ctypes.sizeof(x))
        if hwnd:
            _restore_previous_foreground(hwnd)


@utils.run_if_enabled
def press(key, n, down_time=0.05, up_time=0.1):
    """
    Presses KEY N times, holding it for DOWN_TIME seconds, and releasing for UP_TIME seconds.
    :param key:         The keyboard input to press.
    :param n:           Number of times to press KEY.
    :param down_time:   Duration of down-press (in seconds).
    :param up_time:     Duration of release (in seconds).
    :return:            None
    """

    for _ in range(n):
        key_down(key)
        time.sleep(down_time * (0.8 + 0.4 * random()))
        key_up(key)
        time.sleep(up_time * (0.8 + 0.4 * random()))


@utils.run_if_enabled
def click(position, button='left'):
    """
    Simulate a mouse click with BUTTON at POSITION via PostMessageW (and mouse_event if active).
    :param position:    The (x, y) position at which to click.
    :param button:      Either the left or right mouse button.
    :return:            None
    """

    if button not in ['left', 'right']:
        print(f"'{button}' is not a valid mouse button.")
    else:
        hwnd = _get_target_hwnd()
        if hwnd:
            pt = wintypes.POINT(int(position[0]), int(position[1]))
            user32.ScreenToClient(hwnd, ctypes.byref(pt))
            lparam = ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)
            if button == 'left':
                user32.PostMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
                user32.PostMessageW(hwnd, WM_LBUTTONUP, 0, lparam)
            else:
                user32.PostMessageW(hwnd, WM_RBUTTONDOWN, MK_RBUTTON, lparam)
                user32.PostMessageW(hwnd, WM_RBUTTONUP, 0, lparam)
            _ensure_foreground(hwnd)
        if not hwnd or user32.GetForegroundWindow() == hwnd:
            if button == 'left':
                down_event = win32con.MOUSEEVENTF_LEFTDOWN
                up_event = win32con.MOUSEEVENTF_LEFTUP
            else:
                down_event = win32con.MOUSEEVENTF_RIGHTDOWN
                up_event = win32con.MOUSEEVENTF_RIGHTUP
            win32api.SetCursorPos(position)
            win32api.mouse_event(down_event, position[0], position[1], 0, 0)
            win32api.mouse_event(up_event, position[0], position[1], 0, 0)
        if hwnd:
            _restore_previous_foreground(hwnd)
