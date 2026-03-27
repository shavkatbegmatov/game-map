import cv2
import numpy as np


class FeatureMatcher:
    """Rasmlar orasidagi mos nuqtalarni topuvchi klass."""

    def __init__(self, detector_type: str = "ORB", match_ratio: float = 0.75):
        self.match_ratio = match_ratio

        if detector_type == "ORB":
            self.detector = cv2.ORB_create(nfeatures=5000)
            self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
        elif detector_type == "SIFT":
            self.detector = cv2.SIFT_create(nfeatures=5000)
            self.matcher = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
        else:
            raise ValueError(f"Noma'lum detektor: {detector_type}")

    def find_matches(
        self, img1: np.ndarray, img2: np.ndarray
    ) -> tuple[list, list, list]:
        """Ikki rasm orasidagi mos nuqtalarni topish.

        Returns:
            (keypoints1, keypoints2, good_matches)
        """
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

        kp1, des1 = self.detector.detectAndCompute(gray1, None)
        kp2, des2 = self.detector.detectAndCompute(gray2, None)

        if des1 is None or des2 is None or len(des1) < 2 or len(des2) < 2:
            return kp1, kp2, []

        # KNN matching
        raw_matches = self.matcher.knnMatch(des1, des2, k=2)

        # Lowe's ratio test
        good = []
        for match_pair in raw_matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < self.match_ratio * n.distance:
                    good.append(m)

        return kp1, kp2, good

    def draw_matches(
        self,
        img1: np.ndarray,
        img2: np.ndarray,
        kp1: list,
        kp2: list,
        matches: list,
        max_draw: int = 50,
    ) -> np.ndarray:
        """Match natijalarini vizualizatsiya qilish (debug uchun)."""
        return cv2.drawMatches(
            img1, kp1, img2, kp2, matches[:max_draw], None,
            flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
        )
