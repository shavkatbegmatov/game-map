import re
from pathlib import Path

import cv2
import numpy as np


def load_images(directory: str | Path) -> list[np.ndarray]:
    """Papkadagi raqamlangan PNG rasmlarni tartib bilan yuklash."""
    directory = Path(directory)
    files = sorted(
        [f for f in directory.glob("*.png") if re.match(r"^\d+\.png$", f.name)],
        key=lambda f: int(f.stem),
    )
    if not files:
        raise FileNotFoundError(f"'{directory}' papkasida raqamlangan PNG topilmadi")

    images = []
    for f in files:
        img = cv2.imread(str(f), cv2.IMREAD_UNCHANGED)
        if img is None:
            raise ValueError(f"Rasmni o'qib bo'lmadi: {f}")
        # RGBA bo'lsa BGR ga o'tkazish
        if img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        images.append(img)
        print(f"  Yuklandi: {f.name} ({img.shape[1]}x{img.shape[0]})")

    return images


def save_result(image: np.ndarray, path: str | Path) -> None:
    """Natija rasmni saqlash."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), image)
    print(f"Natija saqlandi: {path} ({image.shape[1]}x{image.shape[0]})")


def crop_black_borders(image: np.ndarray) -> np.ndarray:
    """Qora chekkalarni olib tashlash."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 1, 255, cv2.THRESH_BINARY)
    coords = cv2.findNonZero(thresh)
    if coords is None:
        return image
    x, y, w, h = cv2.boundingRect(coords)
    return image[y : y + h, x : x + w]
