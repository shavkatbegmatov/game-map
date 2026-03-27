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

    @staticmethod
    def _bring_to_foreground(hwnd: int) -> None:
        """O'yin oynasini old planda ko'rsatish."""
        try:
            # Minimized bo'lsa restore qilish
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, 9)  # SW_RESTORE
                time.sleep(0.3)

            # Alt tugma trick — Windows SetForegroundWindow cheklovini chetlab o'tish
            ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # Alt press
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)  # Alt release
            win32gui.SetForegroundWindow(hwnd)
            time.sleep(0.5)
        except Exception:
            pass

    def capture_screenshot(self) -> np.ndarray:
        """O'yin oynasidan bitta screenshot olish (dxcam orqali)."""
        region = self.find_game_window()

        # O'yin oynasini foreground ga olib chiqish
        self._bring_to_foreground(region["hwnd"])

        # Foreground ga chiqqandan keyin koordinatalarni qayta olish
        # (minimized bo'lgan oyna restore bo'lganda pozitsiya o'zgaradi)
        region = self.find_game_window()

        win_left = region["left"]
        win_top = region["top"]
        win_w = region["width"]
        win_h = region["height"]

        if win_w <= 0 or win_h <= 0:
            raise RuntimeError(
                f"O'yin oynasi noto'g'ri o'lchamda: {win_w}x{win_h}. "
                f"Oyna minimized yoki yopiq bo'lishi mumkin."
            )

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

    def _move_camera(self, hwnd: int, direction: str, distance: int = 400) -> None:
        """O'yin kamerasini sichqoncha o'ng tugma + drag bilan siljitish."""
        # Oyna markazini topish
        client_rect = win32gui.GetClientRect(hwnd)
        cx = (client_rect[2] - client_rect[0]) // 2
        cy = (client_rect[3] - client_rect[1]) // 2
        start_x, start_y = win32gui.ClientToScreen(hwnd, (cx, cy))

        # Yo'nalish bo'yicha siljish
        dx, dy = {
            "right": (-distance, 0),
            "left": (distance, 0),
            "up": (0, distance),
            "down": (0, -distance),
        }.get(direction, (-distance, 0))

        end_x = start_x + dx
        end_y = start_y + dy

        # Sichqonchani markazga olib borish
        ctypes.windll.user32.SetCursorPos(start_x, start_y)
        time.sleep(0.05)

        # O'ng tugmani bosish (RIGHTDOWN)
        ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
        time.sleep(0.05)

        # Bosqichma-bosqich siljitish (smooth drag)
        steps = 20
        for step in range(1, steps + 1):
            ix = start_x + dx * step // steps
            iy = start_y + dy * step // steps
            ctypes.windll.user32.SetCursorPos(ix, iy)
            time.sleep(0.01)

        time.sleep(0.05)

        # O'ng tugmani qo'yib yuborish (RIGHTUP)
        ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)
        time.sleep(self.config.capture_delay)

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
        images = []
        for i in range(count):
            print(f"  Screenshot {i + 1}/{count}...")
            img = self.capture_screenshot()
            images.append(img)

            if save_dir:
                path = f"{save_dir}/{i + 1:02d}.png"
                cv2.imwrite(path, img)

            if i < count - 1:
                region = self.find_game_window()
                self._move_camera(region["hwnd"], direction)

        return images
