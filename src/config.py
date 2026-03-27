from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    screenshots_dir: Path = Path("screenshots")
    output_dir: Path = Path("output")
    game_window_title: str = "Erz"
    capture_delay: float = 0.5
    min_match_count: int = 10
    feature_detector: str = "ORB"
    match_ratio: float = 0.75
    blend_width: int = 20
