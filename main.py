"""ERZ Online Map Stitcher — o'yin map parchalarini birlashtiruvchi dastur."""

import argparse
from pathlib import Path

from src.config import Config
from src.image_utils import load_images, save_result
from src.stitcher import MapStitcher


def manual_mode(config: Config, directory: str, output: str, debug: bool) -> None:
    """Qo'lda rejim — papkadagi rasmlarni birlashtirish."""
    print(f"Rasmlar papkasi: {directory}")
    images = load_images(directory)
    print(f"Jami: {len(images)} ta rasm\n")

    stitcher = MapStitcher(config)

    if debug and len(images) >= 2:
        from src.matcher import FeatureMatcher

        fm = FeatureMatcher(config.feature_detector, config.match_ratio)
        kp1, kp2, good = fm.find_matches(images[0], images[1])
        debug_img = fm.draw_matches(images[0], images[1], kp1, kp2, good)
        debug_path = str(Path(output).parent / "debug_matches.png")
        save_result(debug_img, debug_path)

    result = stitcher.stitch_all(images)
    save_result(result, output)
    print("\nBirlashtirish muvaffaqiyatli yakunlandi!")


def auto_mode(
    config: Config, count: int, direction: str, output: str, save_screenshots: bool,
    debug: bool = True,
) -> None:
    """Avtomatik rejim — o'yin oynasidan screenshot olib birlashtirish."""
    from src.capture import GameCapture

    print(f"O'yin oynasi: {config.game_window_title}")
    print(f"Screenshot soni: {count}, Yo'nalish: {direction}\n")

    capture = GameCapture(config)
    save_dir = str(config.screenshots_dir) if save_screenshots else None

    images = capture.capture_sequence(count=count, direction=direction, save_dir=save_dir)
    print(f"\n{len(images)} ta screenshot olindi. Birlashtirish boshlanmoqda...\n")

    if debug and len(images) >= 2:
        from src.matcher import FeatureMatcher

        fm = FeatureMatcher(config.feature_detector, config.match_ratio)
        kp1, kp2, good = fm.find_matches(images[0], images[1])
        debug_img = fm.draw_matches(images[0], images[1], kp1, kp2, good)
        debug_path = str(Path(output).parent / "debug_matches.png")
        save_result(debug_img, debug_path)

    stitcher = MapStitcher(config)
    result = stitcher.stitch_all(images)
    save_result(result, output)
    print("\nBirlashtirish muvaffaqiyatli yakunlandi!")


def main():
    parser = argparse.ArgumentParser(
        description="ERZ Online Map Stitcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Misollar:
  python main.py manual -d screenshots -o output/map.png
  python main.py manual -d . -o output/map.png --detector SIFT
  python main.py auto -n 10 --direction right -o output/map.png
        """,
    )

    subparsers = parser.add_subparsers(dest="mode")

    # Manual rejim
    manual = subparsers.add_parser("manual", help="Qo'lda rejim")
    manual.add_argument(
        "-d", "--directory", default="screenshots", help="Rasmlar papkasi"
    )

    # Auto rejim
    auto = subparsers.add_parser("auto", help="Avtomatik rejim")
    auto.add_argument(
        "-n", "--count", type=int, default=5, help="Screenshot soni"
    )
    auto.add_argument(
        "--direction",
        choices=["right", "left", "up", "down"],
        default="right",
        help="Harakat yo'nalishi",
    )
    auto.add_argument(
        "--save-screenshots",
        action="store_true",
        help="Screenshotlarni saqlash",
    )
    auto.add_argument(
        "--game-title",
        default="Erz",
        help="O'yin oynasi nomi",
    )

    # Umumiy parametrlar
    for sub in [manual, auto]:
        sub.add_argument(
            "-o", "--output", default="output/map.png", help="Natija fayl yo'li"
        )
        sub.add_argument(
            "--detector",
            choices=["ORB", "SIFT"],
            default="ORB",
            help="Feature detector turi",
        )
        sub.add_argument(
            "--ratio",
            type=float,
            default=0.75,
            help="Match ratio chegarasi (0.0-1.0)",
        )
        sub.add_argument(
            "--min-matches",
            type=int,
            default=10,
            help="Minimal match soni",
        )
        sub.add_argument(
            "--debug",
            action="store_true",
            help="Debug rejim (matchlarni vizualizatsiya)",
        )

    args = parser.parse_args()

    # Rejim berilmasa — foydalanuvchidan so'rash
    if args.mode is None:
        print("=" * 50)
        print("  ERZ Online Map Stitcher")
        print("=" * 50)
        print()
        print("Rejimni tanlang:")
        print("  1) manual  — Papkadagi rasmlarni birlashtirish")
        print("  2) auto    — O'yin oynasidan screenshot olib birlashtirish")
        print()
        choice = input("Tanlang (1/2): ").strip()

        if choice != "1":
            args.mode = "auto"
            args.count = int(input("Screenshot soni [5]: ").strip() or "5")
            direction = input("Yo'nalish (right/left/up/down) [right]: ").strip() or "right"
            if direction not in ("right", "left", "up", "down"):
                print(f"Noto'g'ri yo'nalish: {direction}. 'right' ishlatiladi.")
                direction = "right"
            args.direction = direction
            args.save_screenshots = input("Screenshotlarni saqlash? (y/n) [y]: ").strip().lower() != "n"
            args.game_title = input(f"O'yin oynasi nomi [Erz]: ").strip() or "Erz"
        else:
            args.mode = "manual"
            args.directory = input("Rasmlar papkasi [screenshots]: ").strip() or "screenshots"

        args.output = input("Natija fayl yo'li [output/map.png]: ").strip() or "output/map.png"
        args.detector = "ORB"
        args.ratio = 0.75
        args.min_matches = 10
        args.debug = True

    config = Config(
        feature_detector=args.detector,
        match_ratio=args.ratio,
        min_match_count=args.min_matches,
    )

    print("=" * 50)
    print("  ERZ Online Map Stitcher")
    print("=" * 50)
    print(f"Detektor: {config.feature_detector}")
    print(f"Match ratio: {config.match_ratio}")
    print()

    if args.mode == "manual":
        manual_mode(config, args.directory, args.output, args.debug)
    elif args.mode == "auto":
        config.game_window_title = args.game_title
        auto_mode(config, args.count, args.direction, args.output, args.save_screenshots, args.debug)


if __name__ == "__main__":
    main()
