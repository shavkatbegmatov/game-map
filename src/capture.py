import time

import cv2
import numpy as np

from .config import Config

try:
    import mss
except ImportError:
    mss = None

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
        if mss is None:
            raise ImportError("'mss' kutubxonasi o'rnatilmagan: pip install mss")
        self.sct = mss.mss()

    def find_game_window(self) -> dict:
        """O'yin oynasini topish va uning pozitsiyasini qaytarish."""
        if win32gui is None:
            raise ImportError(
                "'pywin32' kutubxonasi o'rnatilmagan: pip install pywin32"
            )

        hwnd = win32gui.FindWindow(None, self.config.game_window_title)
        if not hwnd:
            raise RuntimeError(
                f"O'yin oynasi topilmadi: '{self.config.game_window_title}'"
            )

        rect = win32gui.GetWindowRect(hwnd)
        return {
            "left": rect[0],
            "top": rect[1],
            "width": rect[2] - rect[0],
            "height": rect[3] - rect[1],
        }

    def capture_screenshot(self) -> np.ndarray:
        """O'yin oynasidan bitta screenshot olish."""
        region = self.find_game_window()
        screenshot = self.sct.grab(region)
        img = np.array(screenshot)
        # BGRA -> BGR
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

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
