import time

import cv2
import numpy as np

from .config import Config

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
        self.camera = dxcam.create()

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
        """O'yin oynasini topish va uning pozitsiyasini qaytarish."""
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

        rect = win32gui.GetWindowRect(hwnd)
        return {
            "left": rect[0],
            "top": rect[1],
            "width": rect[2] - rect[0],
            "height": rect[3] - rect[1],
        }

    def capture_screenshot(self) -> np.ndarray:
        """O'yin oynasidan bitta screenshot olish (dxcam orqali)."""
        region = self.find_game_window()
        left, top = region["left"], region["top"]
        right = left + region["width"]
        bottom = top + region["height"]

        img = self.camera.grab(region=(left, top, right, bottom))
        if img is None:
            # Birinchi grab ba'zan None qaytaradi, qayta urinish
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
