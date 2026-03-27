import cv2
import numpy as np

from .config import Config
from .matcher import FeatureMatcher


class MapStitcher:
    """O'yin map parchalarini birlashtiruvchi klass."""

    def __init__(self, config: Config):
        self.config = config
        self.matcher = FeatureMatcher(config.feature_detector, config.match_ratio)

    def stitch_pair(self, img1: np.ndarray, img2: np.ndarray) -> np.ndarray:
        """Ikki rasmni birlashtirish.

        img1 — asosiy rasm (canvas)
        img2 — qo'shiladigan rasm
        """
        kp1, kp2, good_matches = self.matcher.find_matches(img1, img2)

        if len(good_matches) < self.config.min_match_count:
            print(
                f"  Ogohlantirish: faqat {len(good_matches)} match topildi "
                f"(minimum: {self.config.min_match_count}). "
                f"Oddiy yonma-yon qo'shiladi."
            )
            return self._concat_horizontal(img1, img2)

        print(f"  Matchlar soni: {len(good_matches)}")

        # Homography hisoblash
        src_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(
            -1, 1, 2
        )
        dst_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(
            -1, 1, 2
        )
        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

        if H is None:
            print("  Homography topilmadi. Oddiy yonma-yon qo'shiladi.")
            return self._concat_horizontal(img1, img2)

        inliers = mask.ravel().sum() if mask is not None else 0
        print(f"  Inliers: {inliers}/{len(good_matches)}")

        # Pure translation tekshirish
        if self._is_pure_translation(H):
            print("  Pure translation aniqlandi — oddiy siljish ishlatiladi")
            return self._translate_and_blend(img1, img2, H)
        else:
            print("  Perspective warp ishlatiladi")
            return self._warp_and_blend(img1, img2, H)

    def stitch_all(self, images: list[np.ndarray]) -> np.ndarray:
        """Barcha rasmlarni ketma-ket birlashtirish."""
        if len(images) == 0:
            raise ValueError("Rasmlar ro'yxati bo'sh")
        if len(images) == 1:
            return images[0]

        result = images[0]
        for i in range(1, len(images)):
            print(f"\nBirlashtirish: rasm {i} + rasm {i + 1}")
            result = self.stitch_pair(result, images[i])

        return result

    def _is_pure_translation(self, H: np.ndarray, threshold: float = 0.02) -> bool:
        """Homography faqat siljishdan iboratmi."""
        return (
            abs(H[0, 0] - 1) < threshold
            and abs(H[1, 1] - 1) < threshold
            and abs(H[0, 1]) < threshold
            and abs(H[1, 0]) < threshold
            and abs(H[2, 0]) < threshold
            and abs(H[2, 1]) < threshold
        )

    def _translate_and_blend(
        self, img1: np.ndarray, img2: np.ndarray, H: np.ndarray
    ) -> np.ndarray:
        """Oddiy siljish bilan birlashtirish."""
        tx = H[0, 2]
        ty = H[1, 2]

        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        # Yangi canvas o'lchami
        # img2 ni img1 koordinatalariga o'tkazganda uning chegaralari
        corners_img2 = np.array(
            [[0, 0], [w2, 0], [w2, h2], [0, h2]], dtype=np.float32
        )
        corners_img2_transformed = corners_img2 + np.array([tx, ty], dtype=np.float32)

        all_corners = np.vstack(
            [
                np.array([[0, 0], [w1, 0], [w1, h1], [0, h1]], dtype=np.float32),
                corners_img2_transformed,
            ]
        )

        min_x = int(np.floor(all_corners[:, 0].min()))
        min_y = int(np.floor(all_corners[:, 1].min()))
        max_x = int(np.ceil(all_corners[:, 0].max()))
        max_y = int(np.ceil(all_corners[:, 1].max()))

        # Offset — manfiy koordinatalarni musbatga o'tkazish
        offset_x = -min_x if min_x < 0 else 0
        offset_y = -min_y if min_y < 0 else 0

        canvas_w = max_x - min_x
        canvas_h = max_y - min_y

        canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)

        # img1 ni joylashtirish
        canvas[offset_y : offset_y + h1, offset_x : offset_x + w1] = img1

        # img2 ni siljitib joylashtirish (blending bilan)
        y_start = int(round(ty)) + offset_y
        x_start = int(round(tx)) + offset_x

        self._blend_onto_canvas(canvas, img2, x_start, y_start)

        return self._crop_to_content(canvas)

    def _warp_and_blend(
        self, img1: np.ndarray, img2: np.ndarray, H: np.ndarray
    ) -> np.ndarray:
        """Perspective warp bilan birlashtirish."""
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]

        # img2 burchaklarini img1 koordinatalariga o'tkazish
        corners_img2 = np.float32(
            [[0, 0], [w2, 0], [w2, h2], [0, h2]]
        ).reshape(-1, 1, 2)
        corners_transformed = cv2.perspectiveTransform(corners_img2, H)

        all_corners = np.concatenate(
            [
                np.float32([[0, 0], [w1, 0], [w1, h1], [0, h1]]).reshape(-1, 1, 2),
                corners_transformed,
            ]
        )

        min_x = int(np.floor(all_corners[:, 0, 0].min()))
        min_y = int(np.floor(all_corners[:, 0, 1].min()))
        max_x = int(np.ceil(all_corners[:, 0, 0].max()))
        max_y = int(np.ceil(all_corners[:, 0, 1].max()))

        # Translation matritsa — offset uchun
        T = np.array(
            [[1, 0, -min_x], [0, 1, -min_y], [0, 0, 1]], dtype=np.float64
        )

        canvas_w = max_x - min_x
        canvas_h = max_y - min_y

        # img2 ni warp qilish
        warped = cv2.warpPerspective(img2, T @ H, (canvas_w, canvas_h))

        # img1 ni canvas'ga joylashtirish
        canvas = np.zeros_like(warped)
        canvas[-min_y : -min_y + h1, -min_x : -min_x + w1] = img1

        # Blending
        result = self._alpha_blend(canvas, warped)

        return self._crop_to_content(result)

    def _blend_onto_canvas(
        self,
        canvas: np.ndarray,
        img: np.ndarray,
        x_start: int,
        y_start: int,
    ) -> None:
        """Rasmni canvas ustiga blending bilan joylashtirish."""
        h, w = img.shape[:2]
        ch, cw = canvas.shape[:2]

        # Chegaralarni tekshirish
        y_end = min(y_start + h, ch)
        x_end = min(x_start + w, cw)
        y_src_start = max(0, -y_start)
        x_src_start = max(0, -x_start)
        y_start = max(0, y_start)
        x_start = max(0, x_start)

        roi_h = y_end - y_start
        roi_w = x_end - x_start
        if roi_h <= 0 or roi_w <= 0:
            return

        img_crop = img[y_src_start : y_src_start + roi_h, x_src_start : x_src_start + roi_w]
        canvas_roi = canvas[y_start:y_end, x_start:x_end]

        # Overlap mask — ikkala rasmda ham piksel bor joylar
        canvas_gray = cv2.cvtColor(canvas_roi, cv2.COLOR_BGR2GRAY)
        img_gray = cv2.cvtColor(img_crop, cv2.COLOR_BGR2GRAY)
        overlap = (canvas_gray > 0) & (img_gray > 0)

        # Overlap bo'lmagan joylar — to'g'ridan-to'g'ri qo'yish
        no_overlap_canvas = canvas_gray == 0
        canvas_roi[no_overlap_canvas] = img_crop[no_overlap_canvas]

        # Overlap joylar — 50/50 aralashtirish
        if overlap.any():
            canvas_roi[overlap] = (
                canvas_roi[overlap].astype(np.float32) * 0.5
                + img_crop[overlap].astype(np.float32) * 0.5
            ).astype(np.uint8)

    def _alpha_blend(self, img1: np.ndarray, img2: np.ndarray) -> np.ndarray:
        """Ikki rasmni alpha blending bilan birlashtirish."""
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

        mask1 = gray1 > 0
        mask2 = gray2 > 0
        overlap = mask1 & mask2

        result = np.zeros_like(img1)
        # Faqat img1 da bor
        result[mask1 & ~mask2] = img1[mask1 & ~mask2]
        # Faqat img2 da bor
        result[mask2 & ~mask1] = img2[mask2 & ~mask1]
        # Overlap — aralashtirish
        if overlap.any():
            result[overlap] = (
                img1[overlap].astype(np.float32) * 0.5
                + img2[overlap].astype(np.float32) * 0.5
            ).astype(np.uint8)

        return result

    def _crop_to_content(self, image: np.ndarray) -> np.ndarray:
        """Qora chekkalarni olib tashlash."""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        coords = cv2.findNonZero(gray)
        if coords is None:
            return image
        x, y, w, h = cv2.boundingRect(coords)
        return image[y : y + h, x : x + w]

    def _concat_horizontal(self, img1: np.ndarray, img2: np.ndarray) -> np.ndarray:
        """Ikki rasmni oddiy yonma-yon qo'shish (fallback)."""
        h1, w1 = img1.shape[:2]
        h2, w2 = img2.shape[:2]
        max_h = max(h1, h2)
        result = np.zeros((max_h, w1 + w2, 3), dtype=np.uint8)
        result[:h1, :w1] = img1
        result[:h2, w1 : w1 + w2] = img2
        return result
