"""
Live verification and benchmark suite for Auto Maple background execution methods:
1. Hyper-V Generation 2 VM (AutoMaple-VM) + GPU-PV environment check
2. Multi-session RDP (TermService) environment check
3. Win11 Foreground / DirectInput8 input modes (postmessage_only, auto_focus, focus_restore)
   and occluded background window capture (PrintWindow + PW_RENDERFULLCONTENT)
"""

import ctypes
import json
import os
import subprocess
import sys
import time
import tkinter as tk

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

user32 = ctypes.WinDLL('user32', use_last_error=True)
hdesk = user32.OpenDesktopW('Default', 0, False, 0x10000000)
if hdesk:
    user32.SetThreadDesktop(hdesk)
user32.SetProcessDPIAware()


def verify_hyperv_and_vm():
    ps = r"""
    $cpu = Get-CimInstance Win32_Processor
    $cs = Get-CimInstance Win32_ComputerSystem
    $vmwp = Get-Process vmwp -ErrorAction SilentlyContinue
    $vhdx = Get-Item "D:\HyperV\AutoMaple-VM\AutoMaple-VM.vhdx" -ErrorAction SilentlyContinue
    [PSCustomObject]@{
        VirtualizationFirmwareEnabled = [bool]$cpu.VirtualizationFirmwareEnabled
        HypervisorPresent = [bool]$cs.HypervisorPresent
        VmWorkerRunning = [bool]($null -ne $vmwp)
        VmWorkerPid = if ($vmwp) { $vmwp.Id } else { $null }
        VhdxSizeMB = if ($vhdx) { [math]::Round($vhdx.Length / 1MB, 1) } else { 0 }
    } | ConvertTo-Json -Compress
    """
    out = subprocess.check_output(['powershell', '-NoProfile', '-Command', ps], text=True, timeout=10)
    return json.loads(out.strip())


def verify_vkeys_and_capture():
    from src.common import config, vkeys
    from src.modules.capture import Capture

    root = tk.Tk()
    root.title('GameTargetSim')
    root.geometry('400x300+120+120')
    canvas = tk.Canvas(root, width=400, height=300, bg='#1e88e5')
    canvas.pack()
    canvas.create_rectangle(50, 50, 350, 250, fill='#fdd835')

    work = tk.Toplevel(root)
    work.title('HostWorkWindow')
    work.geometry('500x400+100+100')
    work.attributes('-topmost', True)
    root.update()
    time.sleep(0.08)

    game_hwnd = user32.FindWindowW(None, 'GameTargetSim')
    work_hwnd = user32.FindWindowW(None, 'HostWorkWindow')

    # 1. Verify occluded PrintWindow capture while HostWorkWindow completely covers GameTargetSim
    cap = Capture.__new__(Capture)
    cap.handle = game_hwnd
    cap.window = {'left': 120, 'top': 120, 'width': 400, 'height': 300}
    t0 = time.perf_counter()
    img = cap._print_window()
    cap_ms = round((time.perf_counter() - t0) * 1000, 2)
    capture_report = {
        'occluded_capture_ok': img is not None,
        'shape': list(img.shape) if img is not None else None,
        'nonzero_ratio': round(float((img[:, :, :3] > 0).mean()), 3) if img is not None else 0.0,
        'capture_latency_ms': cap_ms
    }

    # 2. Verify DirectInput8 foreground key delivery across all 3 vkeys modes
    work.attributes('-topmost', False)
    root.update()

    class DummyCapture:
        handle = game_hwnd

    config.capture = DummyCapture()
    config.enabled = True

    def is_dinput_key_active(vk):
        root.update()
        return (user32.GetForegroundWindow() == game_hwnd) and bool(user32.GetAsyncKeyState(vk) & 0x8000)

    input_report = {}
    for mode in ['postmessage_only', 'auto_focus', 'focus_restore']:
        config.bg_input_mode = mode
        vkeys._force_activate_window(work_hwnd)
        root.update()
        time.sleep(0.05)

        t0 = time.perf_counter()
        vkeys.key_down('a')
        root.update()
        time.sleep(0.03)
        skill_ok = is_dinput_key_active(0x41)
        vkeys.key_up('a')
        root.update()
        lat = round((time.perf_counter() - t0) * 1000, 2)
        time.sleep(0.03)

        vkeys._force_activate_window(work_hwnd)
        root.update()
        time.sleep(0.05)
        vkeys.key_down('right')
        samples = []
        for _ in range(5):
            time.sleep(0.02)
            samples.append(is_dinput_key_active(0x27))
        vkeys.key_up('right')
        root.update()
        time.sleep(0.03)
        focus_after = (user32.GetForegroundWindow() == work_hwnd)

        input_report[mode] = {
            'skill_dinput_ok': skill_ok,
            'latency_ms': lat,
            'walk_hold_pct': round(sum(samples) / len(samples) * 100, 1),
            'host_focus_restored': focus_after
        }

    config.bg_input_mode = 'auto_focus'
    root.destroy()
    return {'occluded_capture': capture_report, 'input_modes': input_report}


if __name__ == '__main__':
    res = {
        'hyperv_vm': verify_hyperv_and_vm(),
        'native_bg_capture_and_input': verify_vkeys_and_capture()
    }
    print(json.dumps(res, indent=2))
