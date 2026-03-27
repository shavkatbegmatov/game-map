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

    def _send_mouse_input(self, flags: int, dx: int = 0, dy: int = 0) -> None:
        """SendInput orqali mouse event yuborish."""
        import ctypes.wintypes

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [
                ("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", ctypes.c_ulong),
                ("mi", MOUSEINPUT),
            ]

        extra = ctypes.c_ulong(0)
        inp = INPUT()
        inp.type = 0  # INPUT_MOUSE
        inp.mi = MOUSEINPUT(dx, dy, 0, flags, 0, ctypes.pointer(extra))
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

    def _drag_mouse(self, hwnd: int, dx: int, dy: int) -> None:
        """Sichqoncha o'ng tugma bilan drag qilish (SendInput)."""
        client_rect = win32gui.GetClientRect(hwnd)
        cx = (client_rect[2] - client_rect[0]) // 2
        cy = (client_rect[3] - client_rect[1]) // 2
        start_x, start_y = win32gui.ClientToScreen(hwnd, (cx, cy))

        # Sichqonchani markazga
        ctypes.windll.user32.SetCursorPos(start_x, start_y)
        time.sleep(0.1)

        # O'ng tugma bosish
        self._send_mouse_input(0x0008)  # MOUSEEVENTF_RIGHTDOWN
        time.sleep(0.1)

        # Bosqichma-bosqich siljitish
        steps = 40
        for step in range(1, steps + 1):
            ix = start_x + dx * step // steps
            iy = start_y + dy * step // steps
            ctypes.windll.user32.SetCursorPos(ix, iy)
            # MOUSEEVENTF_MOVE signalini yuborish
            self._send_mouse_input(0x0001)  # MOUSEEVENTF_MOVE
            time.sleep(0.015)

        time.sleep(0.1)

        # O'ng tugma qo'yish
        self._send_mouse_input(0x0010)  # MOUSEEVENTF_RIGHTUP
        time.sleep(self.config.capture_delay)

    def _calibrate(self, hwnd: int, direction: str) -> float:
        """Mouse harakati va ekran siljishi nisbatini aniqlash.

        Returns:
            ratio: ekran_siljishi / mouse_siljishi (masalan, 0.33 = 3px mouse = 1px ekran)
        """
        from .matcher import FeatureMatcher

        test_distance = 300  # test uchun mouse px

        print("  Kalibrlash...")
        img_before = self.capture_screenshot()

        dx, dy = {
            "right": (-test_distance, 0),
            "left": (test_distance, 0),
            "up": (0, test_distance),
            "down": (0, -test_distance),
        }.get(direction, (-test_distance, 0))

        self._drag_mouse(hwnd, dx, dy)
        img_after = self.capture_screenshot()

        # Orqaga qaytarish
        self._drag_mouse(hwnd, -dx, -dy)
        time.sleep(0.3)

        # Feature matching bilan haqiqiy siljishni hisoblash
        fm = FeatureMatcher("ORB", 0.75)
        kp1, kp2, good = fm.find_matches(img_before, img_after)

        if len(good) < 10:
            print(f"  Kalibrlash: yetarli match topilmadi ({len(good)}), default 0.33 ishlatiladi")
            return 0.33

        # Median siljishni hisoblash
        shifts = []
        for m in good:
            pt1 = kp1[m.queryIdx].pt
            pt2 = kp2[m.trainIdx].pt
            if direction in ("right", "left"):
                shifts.append(abs(pt1[0] - pt2[0]))
            else:
                shifts.append(abs(pt1[1] - pt2[1]))

        screen_shift = float(np.median(shifts))

        if screen_shift < 1:
            print(f"  Kalibrlash: ekran siljimadi, default 0.33 ishlatiladi")
            return 0.33

        ratio = screen_shift / test_distance
        print(f"  Kalibrlash natijasi: mouse {test_distance}px → ekran {screen_shift:.0f}px (nisbat: {ratio:.2f})")
        return ratio

    def _move_camera(self, hwnd: int, direction: str, screen_distance: int = 400,
                     ratio: float = 0.33) -> None:
        """O'yin kamerasini ma'lum ekran piksel masofasiga siljitish."""
        # screen_distance — ekranda qancha piksel siljishi kerak
        # ratio — ekran/mouse nisbati
        mouse_distance = int(screen_distance / ratio)

        dx, dy = {
            "right": (-mouse_distance, 0),
            "left": (mouse_distance, 0),
            "up": (0, mouse_distance),
            "down": (0, -mouse_distance),
        }.get(direction, (-mouse_distance, 0))

        self._drag_mouse(hwnd, dx, dy)

    def capture_sequence(
        self,
        count: int = 5,
        direction: str = "right",
        save_dir: str | None = None,
        overlap: float = 0.3,
    ) -> list[np.ndarray]:
        """Ketma-ket screenshot olish, o'yinda harakatlanib.

        Args:
            count: Nechta screenshot olish
            direction: Harakat yo'nalishi (right, left, up, down)
            save_dir: Agar berilsa, har bir screenshotni shu papkaga saqlaydi
            overlap: Screenshotlar orasidagi overlap nisbati (0.0-1.0)
        """
        # Birinchi screenshot — oyna o'lchamini bilish uchun
        print(f"  Screenshot 1/{count}...")
        first_img = self.capture_screenshot()
        images = [first_img]

        if save_dir:
            cv2.imwrite(f"{save_dir}/01.png", first_img)

        if count <= 1:
            return images

        h, w = first_img.shape[:2]
        if direction in ("right", "left"):
            screen_distance = int(w * (1 - overlap))
        else:
            screen_distance = int(h * (1 - overlap))

        # Kalibrlash — mouse/ekran nisbatini aniqlash
        region = self.find_game_window()
        ratio = self._calibrate(region["hwnd"], direction)

        print(f"  Har bir qadam: ekranda {screen_distance}px siljish (overlap: {overlap:.0%})\n")

        for i in range(1, count):
            region = self.find_game_window()
            self._move_camera(region["hwnd"], direction, screen_distance, ratio)

            print(f"  Screenshot {i + 1}/{count}...")
            img = self.capture_screenshot()
            images.append(img)

            if save_dir:
                path = f"{save_dir}/{i + 1:02d}.png"
                cv2.imwrite(path, img)

        return images
