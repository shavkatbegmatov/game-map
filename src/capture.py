import ctypes
import time

import cv2
import numpy as np

from .config import Config

# DPI awareness o'rnatish — GetWindowRect fizik piksellar qaytarishi uchun
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-Monitor DPI Aware
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

try:
    import dxcam
except ImportError:
    dxcam = None

try:
    import win32gui
except ImportError:
    win32gui = None

try:
    import keyboard
except ImportError:
    keyboard = None


class GameCapture:
    """O'yin oynasidan avtomatik screenshot oluvchi klass."""

    def __init__(self, config: Config):
        self.config = config
        if dxcam is None:
            raise ImportError("'dxcam' kutubxonasi o'rnatilmagan: pip install dxcam")
        self.camera = None  # capture_screenshot da yaratiladi

    @staticmethod
    def _list_windows() -> list[tuple[int, str]]:
        """Barcha ko'rinadigan oynalar ro'yxatini qaytarish."""
        windows = []

        def callback(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title:
                    windows.append((hwnd, title))

        win32gui.EnumWindows(callback, None)
        return windows

    def find_game_window(self) -> dict:
        """O'yin oynasini topish va uning klient maydonini qaytarish."""
        if win32gui is None:
            raise ImportError(
                "'pywin32' kutubxonasi o'rnatilmagan: pip install pywin32"
            )

        target = self.config.game_window_title

        # 1) To'liq moslik
        hwnd = win32gui.FindWindow(None, target)

        # 2) Qisman moslik — oyna nomida target mavjud bo'lsa
        if not hwnd:
            target_lower = target.lower()
            for h, title in self._list_windows():
                if target_lower in title.lower():
                    hwnd = h
                    print(f"  Oyna topildi (qisman moslik): '{title}'")
                    break

        if not hwnd:
            similar = [
                title for _, title in self._list_windows()
                if any(word.lower() in title.lower() for word in target.split())
            ]
            hint = ""
            if similar:
                hint = "\n  O'xshash oynalar:\n" + "\n".join(f"    - {t}" for t in similar[:10])
            raise RuntimeError(
                f"O'yin oynasi topilmadi: '{target}'{hint}\n"
                f"  O'yin ochiq ekanligiga ishonch hosil qiling."
            )

        # Klient maydoni — oyna ramkasi va sarlavhasiz, faqat o'yin kontenti
        client_rect = win32gui.GetClientRect(hwnd)
        left, top = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))
        width = client_rect[2] - client_rect[0]
        height = client_rect[3] - client_rect[1]

        return {
            "hwnd": hwnd,
            "left": left,
            "top": top,
            "width": width,
            "height": height,
        }

    def _find_monitor_index(self, window_left: int, window_top: int) -> int:
        """Oyna qaysi monitorda ekanini aniqlash."""
        try:
            from ctypes import windll, byref, Structure, c_long, POINTER, WINFUNCTYPE, c_int
            import ctypes

            hmon = windll.user32.MonitorFromPoint(
                ctypes.wintypes.POINT(window_left, window_top), 1  # MONITOR_DEFAULTTONEAREST
            )

            class MONITORINFO(Structure):
                _fields_ = [
                    ("cbSize", c_long),
                    ("rcMonitor", ctypes.wintypes.RECT),
                    ("rcWork", ctypes.wintypes.RECT),
                    ("dwFlags", c_long),
                ]

            info = MONITORINFO()
            info.cbSize = ctypes.sizeof(MONITORINFO)
            windll.user32.GetMonitorInfoW(hmon, byref(info))

            # dxcam monitor indeksini topish — barcha output'larni tekshirish
            outputs = dxcam.device_info()
            for idx, dev in enumerate(outputs):
                if dev.get("left") == info.rcMonitor.left and dev.get("top") == info.rcMonitor.top:
                    return idx
        except Exception:
            pass
        return 0

    def capture_screenshot(self) -> np.ndarray:
        """O'yin oynasidan bitta screenshot olish (dxcam orqali)."""
        region = self.find_game_window()
        win_left = region["left"]
        win_top = region["top"]
        win_w = region["width"]
        win_h = region["height"]

        # Camera yaratish yoki qayta yaratish (monitor o'zgarishi mumkin)
        if self.camera is None:
            self.camera = dxcam.create(output_idx=0)

        # Region ni ekran chegarasiga moslashtirish
        scr_w = self.camera.width
        scr_h = self.camera.height

        left = max(0, min(win_left, scr_w - 1))
        top = max(0, min(win_top, scr_h - 1))
        right = max(left + 1, min(win_left + win_w, scr_w))
        bottom = max(top + 1, min(win_top + win_h, scr_h))

        print(f"  Ekran: {scr_w}x{scr_h}, Oyna: left={win_left}, top={win_top}, {win_w}x{win_h}")
        print(f"  Capture region: ({left}, {top}, {right}, {bottom})")

        img = self.camera.grab(region=(left, top, right, bottom))
        if img is None:
            time.sleep(0.1)
            img = self.camera.grab(region=(left, top, right, bottom))
        if img is None:
            raise RuntimeError("Screenshot olib bo'lmadi (dxcam None qaytardi)")

        # dxcam RGB formatda qaytaradi, BGR ga o'tkazamiz
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def capture_sequence(
        self,
        count: int = 5,
        direction: str = "right",
        save_dir: str | None = None,
    ) -> list[np.ndarray]:
        """Ketma-ket screenshot olish, o'yinda harakatlanib.

        Args:
            count: Nechta screenshot olish
            direction: Harakat yo'nalishi (right, left, up, down)
            save_dir: Agar berilsa, har bir screenshotni shu papkaga saqlaydi
        """
        if keyboard is None:
            raise ImportError(
                "'keyboard' kutubxonasi o'rnatilmagan: pip install keyboard"
            )

        key_map = {
            "right": "right",
            "left": "left",
            "up": "up",
            "down": "down",
        }
        key = key_map.get(direction, "right")

        images = []
        for i in range(count):
            print(f"  Screenshot {i + 1}/{count}...")
            img = self.capture_screenshot()
            images.append(img)

            if save_dir:
                path = f"{save_dir}/{i + 1:02d}.png"
                cv2.imwrite(path, img)

            if i < count - 1:
                # O'yinda harakatlanish
                keyboard.press(key)
                time.sleep(0.15)
                keyboard.release(key)
                time.sleep(self.config.capture_delay)

        return images
