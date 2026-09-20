"""抓帧权限验证探针:结果写 logs/probe_result.txt。"""
import ctypes, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ctypes.windll.shcore.SetProcessDpiAwareness(1)

lines = [f"is_admin={bool(ctypes.windll.shell32.IsUserAnAdmin())}"]
from window.manager import WindowManager
from vision.capture import ScreenCapture
wm = WindowManager()
wins = wm.get_windows("MuMu")
if not wins:
    lines.append("window=NOT_FOUND")
else:
    hwnd = wins[0].hwnd
    cap = ScreenCapture()
    import cv2
    log_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "logs")
    for i in range(3):
        try:
            img = cap.capture(hwnd)
            cv2.imwrite(os.path.join(log_dir, f"probe_{i}.png"), img)
            lines.append(f"frame{i}=OK {img.shape[1]}x{img.shape[0]} mean={float(img.mean()):.1f}")
        except Exception as e:
            lines.append(f"frame{i}=FAIL {e}")
        time.sleep(0.5)
out = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "logs", "probe_result.txt")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print("\n".join(lines))
