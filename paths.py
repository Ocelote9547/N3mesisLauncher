import os
import sys
from pathlib import Path

APP_NAME = "N3mesisLauncher"


def application_dir() -> Path:
    """Directorio donde se ejecuta el launcher."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def resource_path(relative_path: str) -> Path:
    """
    Obtiene una ruta válida tanto en desarrollo como
    cuando el launcher está compilado con PyInstaller.
    """
    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = application_dir()

    return base / relative_path


def minecraft_dir() -> Path:
    """
    Devuelve la carpeta .minecraft del usuario.
    """
    appdata = os.getenv("APPDATA")

    if appdata:
        return Path(appdata) / ".minecraft"

    return Path.home() / ".minecraft"


def launcher_dir(mc_dir: Path | None = None) -> Path:
    """
    Carpeta propia del launcher.
    """
    path = (mc_dir or minecraft_dir()) / "launcher"
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_dir(mc_dir: Path | None = None) -> Path:
    """
    Java descargado por N3mesis.
    """
    path = launcher_dir(mc_dir) / "runtime"
    path.mkdir(parents=True, exist_ok=True)
    return path


def downloads_dir(mc_dir: Path | None = None) -> Path:
    """
    Descargas temporales.
    """
    path = launcher_dir(mc_dir) / "downloads"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path(mc_dir: Path | None = None) -> Path:
    """
    Configuración del launcher.
    """
    return launcher_dir(mc_dir) / "config.json"


def mods_dir(mc_dir: Path | None = None) -> Path:
    """
    Carpeta de mods.
    """
    path = minecraft_dir() if mc_dir is None else mc_dir
    mods = path / "mods"
    mods.mkdir(parents=True, exist_ok=True)
    return mods


def skins_dir(mc_dir: Path | None = None) -> Path:
    """
    (Compatibilidad temporal)

    Más adelante desaparecerá cuando eliminemos
    completamente el sistema de skins.
    """
    path = launcher_dir(mc_dir) / "skins"
    path.mkdir(parents=True, exist_ok=True)
    return path