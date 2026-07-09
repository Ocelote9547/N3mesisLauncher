import sys

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from launcher import MinecraftLauncher
from main_window import MainWindow
from paths import minecraft_dir, resource_path


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("N3mesis Launcher")

    icon_path = resource_path("icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    launcher = MinecraftLauncher(minecraft_dir())
    window = MainWindow(launcher)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
