"""End-to-end live verification:
1. Mudfish Maple Guard (http://127.0.0.1:18282) daemon & US West (SID #3) Full VPN tunnel verification
2. MapleStory launch via Nexon Launcher over US West VPN
3. win-bg-pipeline Probe + 5-frame PrintWindow Capture Benchmark + Input Verification
4. Auto Maple live GUI + minimap/player tracking verification
"""

import ctypes
import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
import cv2
import numpy as np

AUTO_MAPLE_DIR = r"C:\Users\icand\.gemini\antigravity\scratch\auto-maple"
PIPELINE_DIR = r"C:\Users\icand\.gemini\antigravity\scratch\win-bg-pipeline"
MUDFISH_GUARD_DIR = r"C:\Users\icand\.gemini\antigravity\scratch\mudfish-maple-guard"
ARTIFACT_DIR = r"C:\Users\icand\.gemini\antigravity\brain\c16a3615-170a-4b7a-966c-9306c1e35456"
REPORT_PATH = os.path.join(AUTO_MAPLE_DIR, "live_verify_report.json")

os.chdir(AUTO_MAPLE_DIR)
for d in (AUTO_MAPLE_DIR, PIPELINE_DIR, MUDFISH_GUARD_DIR):
    if d not in sys.path:
        sys.path.insert(0, d)

from win_bg_pipeline.win32_api import shell32, user32, RECT
from win_bg_pipeline.probe import probe_window, enumerate_windows
from win_bg_pipeline.capture_pipeline import CapturePipeline
from win_bg_pipeline.input_pipeline import InputPipeline, compute_frame_diff_ratio


def ensure_elevated():
    if shell32.IsUserAnAdmin():
        return True
    if "--worker" in sys.argv:
        return False

    for p in [
        REPORT_PATH,
        os.path.join(ARTIFACT_DIR, "live_nexon_launcher.png"),
        os.path.join(ARTIFACT_DIR, "live_maple_before.png"),
        os.path.join(ARTIFACT_DIR, "live_maple_after.png"),
        os.path.join(ARTIFACT_DIR, "live_auto_maple_gui.png"),
    ]:
        with open(p, "wb") as f:
            f.write(b"")

    start_ts = time.time()
    params = f'"{os.path.abspath(__file__)}" --worker'
    ret = shell32.ShellExecuteW(None, "runas", sys.executable, params, AUTO_MAPLE_DIR, 1)
    if int(ret) <= 32:
        return True

    print("[~] Waiting for elevated verification worker to complete...")
    for _ in range(180):
        time.sleep(1.0)
        if os.path.exists(REPORT_PATH) and os.path.getsize(REPORT_PATH) > 10:
            try:
                with open(REPORT_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("completed_at", 0) > start_ts:
                    print(json.dumps(data, ensure_ascii=False, indent=2))
                    sys.exit(0)
            except Exception:
                pass
    print("[!] Timed out waiting for elevated worker.")
    sys.exit(1)


def http_json(url, method="GET", payload=None, timeout=12):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "ignore"))


def ensure_mudfish_auto_vpn() -> dict:
    """Ensure Mudfish Maple Guard server (127.0.0.1:18282) is running and US West Full VPN (SID #3) is active."""
    guard_url = "http://127.0.0.1:18282"
    server_alive = False
    try:
        st = http_json(f"{guard_url}/api/state", timeout=3)
        server_alive = True
    except Exception:
        pass

    if not server_alive:
        subprocess.Popen(
            [sys.executable, os.path.join(MUDFISH_GUARD_DIR, "server.py")],
            cwd=MUDFISH_GUARD_DIR,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        for _ in range(15):
            time.sleep(1.0)
            try:
                st = http_json(f"{guard_url}/api/state", timeout=3)
                server_alive = True
                break
            except Exception:
                pass

    # Connect to US West (SID #3) and ensure Full VPN is ready
    try:
        res = http_json(f"{guard_url}/api/connect-us", method="POST", payload={"sid": 3}, timeout=25)
        state = res.get("state") or http_json(f"{guard_url}/api/state", timeout=6)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    # Wait up to 15s for coreReady & fullvpnEnabled
    for _ in range(15):
        daemon = state.get("daemon") or {}
        if daemon.get("coreReady") and daemon.get("fullvpnEnabled"):
            break
        time.sleep(1.0)
        try:
            state = http_json(f"{guard_url}/api/state", timeout=5)
        except Exception:
            pass

    daemon = state.get("daemon") or {}
    myip = state.get("myip") or {}
    return {
        "guard_server_port": 18282,
        "ok": bool(state.get("ok")),
        "isSignedIn": daemon.get("isSignedIn"),
        "coreRunning": daemon.get("coreRunning"),
        "coreReady": daemon.get("coreReady"),
        "fullvpnEnabled": daemon.get("fullvpnEnabled"),
        "fullvpnSid": daemon.get("fullvpnSid"),
        "username": daemon.get("username"),
        "credits": daemon.get("credits"),
        "public_ip": myip.get("remote_addr"),
        "vpn_location": myip.get("location") or myip.get("country"),
        "recent_logs": (state.get("logs") or [])[:5],
    }


def find_maple_hwnd():
    hwnd = user32.FindWindowW("MapleStoryClass", None) or user32.FindWindowW(None, "MapleStory")
    if hwnd and user32.IsWindow(hwnd):
        return hwnd
    cands = enumerate_windows(class_name="MapleStoryClass", visible_only=False)
    return cands[0].hwnd if cands else 0


def launch_maple_via_nexon_launcher(cap_pipe: CapturePipeline, inp_pipe: InputPipeline) -> tuple[int, list[dict]]:
    launcher_logs = []
    hwnd = find_maple_hwnd()
    if hwnd:
        return hwnd, launcher_logs

    cands = enumerate_windows(process_name="nexon_client.exe", visible_only=True)
    for c in cands:
        launcher_logs.append({
            "hwnd": c.hwnd,
            "pid": c.pid,
            "class_name": c.class_name,
            "title": c.title,
            "size": f"{c.width}x{c.height}",
        })
        if 750 <= c.width <= 850 and 480 <= c.height <= 560:
            user32.PostMessageW(c.hwnd, 0x0010, 0, 0)
            time.sleep(0.4)

    # Trigger direct protocol launch now that US West Full VPN is active
    launcher_exe = r"C:\Program Files (x86)\Nexon\Nexon Launcher\nexon_launcher.exe"
    if os.path.exists(launcher_exe):
        subprocess.Popen([launcher_exe, "nxl://launch/59813"], cwd=os.path.dirname(launcher_exe))
    time.sleep(2.0)

    main_wins = [c for c in cands if c.class_name == "Chrome_WidgetWin_1" and c.width >= 960 and c.height >= 680]
    if main_wins:
        mw = main_wins[0]
        user32.ShowWindow(mw.hwnd, 9)
        time.sleep(0.5)
        inp_pipe._foreground_click_guarded(mw.hwnd, 148, 403, "left", 0.12)
        time.sleep(2.0)
        cap_pipe.capture(mw.hwnd, output_png=os.path.join(ARTIFACT_DIR, "live_nexon_launcher.png"))

    # Wait up to 45s for MapleStoryClass to appear
    for _ in range(30):
        hwnd = find_maple_hwnd()
        if hwnd:
            return hwnd, launcher_logs
        cur_cands = enumerate_windows(process_name="nexon_client.exe", visible_only=True)
        for cw in cur_cands:
            if cw.class_name == "Chrome_WidgetWin_1" and 250 <= cw.width < 750 and 150 <= cw.height < 550:
                cap = cap_pipe.capture(cw.hwnd)
                if cap.success and cap.bgra_bytes:
                    img = np.frombuffer(cap.bgra_bytes, dtype=np.uint8).reshape((cap.height, cap.width, 4))[:, :, :3]
                    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
                    mask = cv2.inRange(hsv, np.array([95, 120, 150]), np.array([130, 255, 255]))
                    ys, xs = np.where(mask > 0)
                    if len(xs) > 80:
                        inp_pipe._foreground_click_guarded(
                            cw.hwnd, int(np.median(xs)), int(np.median(ys)), "left", 0.08
                        )
        time.sleep(1.5)

    return find_maple_hwnd(), launcher_logs


def main():
    ensure_elevated()
    report = {
        "is_admin": bool(shell32.IsUserAnAdmin()),
        "mudfish_auto_vpn": None,
        "nexon_launcher_windows": [],
        "maple_hwnd": 0,
        "probe": None,
        "capture_benchmark": None,
        "input_verification": None,
        "auto_maple": None,
        "error": None,
        "completed_at": 0,
    }
    try:
        # 1. Verify and activate Mudfish Auto-VPN (US West SID #3)
        report["mudfish_auto_vpn"] = ensure_mudfish_auto_vpn()

        cap_pipe = CapturePipeline(auto_unminimize_noactivate=True)
        inp_pipe_bg = InputPipeline(capture_pipeline=cap_pipe, allow_foreground_fallback=False)
        inp_pipe_fg = InputPipeline(capture_pipeline=cap_pipe, allow_foreground_fallback=True)

        # 2. Launch MapleStory over US West VPN
        maple_hwnd, launcher_logs = launch_maple_via_nexon_launcher(cap_pipe, inp_pipe_fg)
        report["nexon_launcher_windows"] = launcher_logs
        report["maple_hwnd"] = maple_hwnd

        if maple_hwnd:
            for _ in range(35):
                rc = RECT()
                user32.GetWindowRect(maple_hwnd, ctypes.byref(rc))
                if rc.width >= 800 and rc.height >= 600 and not user32.IsIconic(maple_hwnd):
                    break
                user32.PostMessageW(maple_hwnd, 0x0112, 0xF120, 0)
                user32.ShowWindow(maple_hwnd, 9)
                time.sleep(1.0)
                maple_hwnd = find_maple_hwnd() or maple_hwnd

            for _ in range(35):
                cap_test = cap_pipe.capture(maple_hwnd)
                if (
                    cap_test.success
                    and cap_test.validation
                    and 15.0 < cap_test.validation.mean_luma < 245.0
                    and cap_test.validation.std_luma > 20.0
                ):
                    break
                time.sleep(1.0)

            probe_rep = probe_window(hwnd=maple_hwnd)
            report["probe"] = probe_rep.to_dict()

            latencies = []
            last_cap = None
            for i in range(5):
                t0 = time.perf_counter()
                out_p = os.path.join(ARTIFACT_DIR, "live_maple_before.png") if i == 4 else None
                c = cap_pipe.capture(maple_hwnd, output_png=out_p)
                latencies.append(round((time.perf_counter() - t0) * 1000.0, 2))
                last_cap = c

            if last_cap and last_cap.validation:
                report["capture_benchmark"] = {
                    "success": last_cap.success,
                    "winning_stage": last_cap.winning_stage,
                    "resolution": f"{last_cap.width}x{last_cap.height}",
                    "latencies_ms": latencies,
                    "avg_latency_ms": round(sum(latencies) / len(latencies), 2),
                    "fps_equivalent": round(1000.0 / (sum(latencies) / len(latencies)), 1),
                    "mean_luma": last_cap.validation.mean_luma,
                    "std_luma": last_cap.validation.std_luma,
                    "non_black_ratio": last_cap.validation.non_black_ratio,
                    "unique_sampled_colors": last_cap.validation.unique_sampled_colors,
                }

            bg_only_res = inp_pipe_bg.send_click(
                maple_hwnd,
                985,
                435,
                button="left",
                verify_visual_change=True,
            )
            fg_guard_res = inp_pipe_fg.send_click(
                maple_hwnd,
                985,
                435,
                button="left",
                verify_visual_change=True,
            )
            after_cap = cap_pipe.capture(
                maple_hwnd,
                output_png=os.path.join(ARTIFACT_DIR, "live_maple_after.png"),
            )
            total_diff = 0.0
            if last_cap and after_cap and last_cap.bgra_bytes and after_cap.bgra_bytes:
                total_diff = compute_frame_diff_ratio(last_cap.bgra_bytes, after_cap.bgra_bytes)

            report["input_verification"] = {
                "background_postmessage_only": {
                    "stage": bg_only_res.winning_stage,
                    "visual_diff_ratio": bg_only_res.visual_diff_ratio,
                    "success": bg_only_res.success,
                },
                "foreground_guarded_sendinput": {
                    "stage": fg_guard_res.winning_stage,
                    "visual_diff_ratio": fg_guard_res.visual_diff_ratio,
                    "success": fg_guard_res.success,
                },
                "before_after_diff_ratio": total_diff,
            }

        auto_hwnd = user32.FindWindowW(None, "Auto Maple")
        if not auto_hwnd:
            subprocess.Popen(
                [sys.executable, os.path.join(AUTO_MAPLE_DIR, "main.py"), "--no-elevate"],
                cwd=AUTO_MAPLE_DIR,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            )
            for _ in range(25):
                time.sleep(0.3)
                auto_hwnd = user32.FindWindowW(None, "Auto Maple")
                if auto_hwnd:
                    break

        from src.common import utils as am_utils
        from src.modules.capture import (
            MM_TL_TEMPLATE,
            MM_BR_TEMPLATE,
            PLAYER_TEMPLATE,
            MINIMAP_TOP_BORDER,
            MINIMAP_BOTTOM_BORDER,
            MMT_WIDTH,
            MMT_HEIGHT,
            PT_WIDTH,
            PT_HEIGHT,
        )

        live_frame_path = os.path.join(ARTIFACT_DIR, "live_maple_before.png")
        ingame_ref_path = r"C:\Users\icand\.gemini\antigravity\brain\82a78e92-9943-4ee6-b4a2-dd7bcb012d22\scratch\maple_bg_before.png"
        test_frame = cv2.imread(live_frame_path) if os.path.exists(live_frame_path) and os.path.getsize(live_frame_path) > 100 else None

        mm_calibrated = False
        player_pts = []
        if test_frame is not None:
            tl, _ = am_utils.single_match(test_frame, MM_TL_TEMPLATE)
            _, br = am_utils.single_match(test_frame, MM_BR_TEMPLATE)
            if tl[0] <= 150 and tl[1] <= 250 and (br[0] - tl[0] > MMT_WIDTH) and (br[1] - tl[1] > MMT_HEIGHT):
                mm_calibrated = True
                mm_tl = (tl[0] + MINIMAP_BOTTOM_BORDER, tl[1] + MINIMAP_TOP_BORDER)
                mm_br = (max(mm_tl[0] + PT_WIDTH, br[0] - MINIMAP_BOTTOM_BORDER), max(mm_tl[1] + PT_HEIGHT, br[1] - MINIMAP_BOTTOM_BORDER))
                minimap = test_frame[mm_tl[1]:mm_br[1], mm_tl[0]:mm_br[0]]
                player_pts = am_utils.multi_match(minimap, PLAYER_TEMPLATE, threshold=0.8)

        ingame_test_ok = False
        ingame_player_pts = []
        ingame_frame = cv2.imread(ingame_ref_path)
        if ingame_frame is not None:
            tl2, _ = am_utils.single_match(ingame_frame, MM_TL_TEMPLATE)
            _, br2 = am_utils.single_match(ingame_frame, MM_BR_TEMPLATE)
            if tl2[0] <= 150 and tl2[1] <= 250 and (br2[0] - tl2[0] > MMT_WIDTH) and (br2[1] - tl2[1] > MMT_HEIGHT):
                ingame_test_ok = True
                mm_tl2 = (tl2[0] + MINIMAP_BOTTOM_BORDER, tl2[1] + MINIMAP_TOP_BORDER)
                mm_br2 = (max(mm_tl2[0] + PT_WIDTH, br2[0] - MINIMAP_BOTTOM_BORDER), max(mm_tl2[1] + PT_HEIGHT, br2[1] - MINIMAP_BOTTOM_BORDER))
                minimap2 = ingame_frame[mm_tl2[1]:mm_br2[1], mm_tl2[0]:mm_br2[0]]
                ingame_player_pts = am_utils.multi_match(minimap2, PLAYER_TEMPLATE, threshold=0.8)

        auto_cap_ok = False
        time.sleep(1.5)
        auto_hwnd = user32.FindWindowW(None, "Auto Maple")
        if auto_hwnd and user32.IsWindow(auto_hwnd):
            try:
                ac = cap_pipe.capture(auto_hwnd, output_png=os.path.join(ARTIFACT_DIR, "live_auto_maple_gui.png"))
                auto_cap_ok = ac.success
            except Exception:
                pass

        report["auto_maple"] = {
            "gui_hwnd": auto_hwnd,
            "gui_capture_success": auto_cap_ok,
            "live_window_minimap_active": mm_calibrated,
            "live_window_player_points": player_pts,
            "ingame_map_minimap_calibrated": ingame_test_ok,
            "ingame_map_player_points": ingame_player_pts,
        }
    except Exception:
        report["error"] = traceback.format_exc()

    report["completed_at"] = time.time()
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
