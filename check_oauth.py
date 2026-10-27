"""Capture all visible nexon_client.exe windows."""

import json
import os
import sys
import time

AUTO_MAPLE_DIR = r"C:\Users\icand\.gemini\antigravity\scratch\auto-maple"
PIPELINE_DIR = r"C:\Users\icand\.gemini\antigravity\scratch\win-bg-pipeline"
ARTIFACT_DIR = r"C:\Users\icand\.gemini\antigravity\brain\c16a3615-170a-4b7a-966c-9306c1e35456"
OAUTH_REPORT = os.path.join(AUTO_MAPLE_DIR, "oauth_windows.json")

sys.path.insert(0, PIPELINE_DIR)
from win_bg_pipeline.win32_api import shell32
from win_bg_pipeline.probe import enumerate_windows
from win_bg_pipeline.capture_pipeline import CapturePipeline


def main():
    if not shell32.IsUserAnAdmin() and "--worker" not in sys.argv:
        for p in [OAUTH_REPORT, os.path.join(ARTIFACT_DIR, "live_nexon_launcher.png")]:
            with open(p, "wb") as f:
                f.write(b"")
        t0 = time.time()
        shell32.ShellExecuteW(None, "runas", sys.executable, f'"{os.path.abspath(__file__)}" --worker', AUTO_MAPLE_DIR, 1)
        for _ in range(30):
            time.sleep(0.5)
            if os.path.exists(OAUTH_REPORT) and os.path.getsize(OAUTH_REPORT) > 5:
                try:
                    with open(OAUTH_REPORT, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    if d.get("ts", 0) > t0:
                        print(json.dumps(d, ensure_ascii=False, indent=2))
                        return
                except Exception:
                    pass
        return

    cap_pipe = CapturePipeline()
    wins = enumerate_windows(process_name="nexon_client.exe", visible_only=True)
    captured = []
    for w in wins:
        if w.width >= 300 and w.height >= 200:
            if w.width >= 900:
                cap_pipe.capture(w.hwnd, output_png=os.path.join(ARTIFACT_DIR, "live_nexon_launcher.png"))
            captured.append({"hwnd": w.hwnd, "size": f"{w.width}x{w.height}", "title": w.title})

    with open(OAUTH_REPORT, "w", encoding="utf-8") as f:
        json.dump({"ts": time.time(), "captured": captured}, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
