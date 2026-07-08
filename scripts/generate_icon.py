"""Generate assets/icon.ico for PyInstaller builds."""

from __future__ import annotations

from pathlib import Path

from unmouse.launcher.tray import create_tray_icon_image


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    icon_path = repo_root / "assets" / "icon.ico"
    icon_path.parent.mkdir(parents=True, exist_ok=True)
    image = create_tray_icon_image(64)
    image.save(icon_path, format="ICO", sizes=[(64, 64), (32, 32), (16, 16)])
    print(f"Wrote {icon_path}")


if __name__ == "__main__":
    main()
