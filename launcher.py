import os
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

import minecraft_launcher_lib
import requests

from paths import runtime_dir

JAVA_URLS = {
    8: "https://api.adoptium.net/v3/binary/latest/8/ga/windows/x64/jdk/hotspot/normal/eclipse",
    17: "https://api.adoptium.net/v3/binary/latest/17/ga/windows/x64/jdk/hotspot/normal/eclipse",
    21: "https://api.adoptium.net/v3/binary/latest/21/ga/windows/x64/jdk/hotspot/normal/eclipse",
}

ProgressCallback = Callable[[str, int, int], None]


class ProgressReporter:
    def __init__(self, callback: ProgressCallback | None):
        self.callback = callback
        self.status = "Preparando"
        self.current = 0
        self.total = 0

    def set_status(self, status: str) -> None:
        self.status = status
        self.emit()

    def set_progress(self, current: int) -> None:
        self.current = current
        self.emit()

    def set_max(self, total: int) -> None:
        self.total = max(total, 0)
        self.current = 0
        self.emit()

    def emit(self) -> None:
        if self.callback:
            self.callback(self.status, self.current, self.total)

    def as_dict(self) -> dict[str, Callable]:
        return {
            "setStatus": self.set_status,
            "setProgress": self.set_progress,
            "setMax": self.set_max,
        }


class MinecraftLauncher:
    def __init__(self, mc_dir: str | os.PathLike):
        self.mc_dir = Path(mc_dir)
        self._cancel = False
        self.process: subprocess.Popen | None = None

    def cancel(self) -> None:
        self._cancel = True

    def launcher_dir(self) -> Path:
        path = self.mc_dir / "launcher"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def runtime_dir(self) -> Path:
        return runtime_dir(self.mc_dir)

    def java_installations(self) -> list[dict[str, str]]:
        installations = []
        found = set()

        def add(name: str, path: Path, source: str):
            if not path.exists():
                return

            real = str(path.resolve())

            if real in found:
                return

            found.add(real)

            installations.append(
                {
                    "name": name,
                    "path": real,
                    "source": source,
                }
            )

        # Java descargado por el launcher
        for version in JAVA_URLS:
            root = runtime_dir(self.mc_dir) / f"java{version}"
            java = self._find_javaw(root)

            if java:
                add(f"Java {version}", java, "N3mesis")

        # JAVA_HOME
        java_home = os.getenv("JAVA_HOME")

        if java_home:
            add(
                "JAVA_HOME",
                Path(java_home) / "bin" / "javaw.exe",
                "Sistema",
            )

        # PATH
        java = shutil.which("javaw")

        if java:
            add(
                "Java del sistema",
                Path(java),
                "PATH",
            )

        # Program Files
        possible = [
            Path("C:/Program Files/Java"),
            Path("C:/Program Files/Eclipse Adoptium"),
            Path("C:/Program Files/Microsoft"),
        ]

        for folder in possible:

            if not folder.exists():
                continue

            for java in folder.glob("**/javaw.exe"):
                add(
                    java.parent.parent.name,
                    java,
                    "Instalado",
                )

        return installations

    def required_java(self, mc_version: str, is_forge: bool = False) -> int:
        if is_forge and mc_version.startswith("1.20.1"):
            return 17
        if mc_version.startswith("1.21") or mc_version.startswith("1.20.5"):
            return 21
        if mc_version.startswith(("1.18", "1.19", "1.20")):
            return 17
        if mc_version.startswith(("1.12", "1.13", "1.14", "1.15", "1.16")):
            return 8
        return 17

    def _find_javaw(self, root: Path) -> Path | None:
        direct = root / "bin" / "javaw.exe"
        if direct.exists():
            return direct
        matches = list(root.glob("**/bin/javaw.exe"))
        return matches[0] if matches else None

    def download_java(self, version: int, callback: ProgressCallback | None = None) -> Path:
        url = JAVA_URLS.get(version)
        if not url:
            raise RuntimeError(f"No hay URL de Java para la version {version}")

        target_dir = self.runtime_dir() / f"java{version}"
        java_bin = self._find_javaw(target_dir)
        if java_bin:
            return java_bin.parent.parent

        zip_path = self.runtime_dir() / f"java{version}.zip"
        callback and callback(f"Descargando Java {version}", 0, 100)

        with requests.get(url, stream=True, timeout=30) as response:
            response.raise_for_status()
            total = int(response.headers.get("content-length", "0"))
            downloaded = 0
            with zip_path.open("wb") as f:
                for chunk in response.iter_content(1024 * 256):
                    if self._cancel:
                        raise RuntimeError("Operacion cancelada")
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded += len(chunk)
                    callback and callback(f"Descargando Java {version}", downloaded, total)

        callback and callback(f"Instalando Java {version}", 0, 1)
        with tempfile.TemporaryDirectory(prefix=f"n3mesis-java{version}-") as tmp:
            tmp_path = Path(tmp)
            with zipfile.ZipFile(zip_path, "r") as archive:
                archive.extractall(tmp_path)

            extracted_java = self._find_javaw(tmp_path)
            if not extracted_java:
                raise RuntimeError("No se encontro javaw.exe en el paquete descargado")

            source_root = extracted_java.parent.parent
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(source_root, target_dir)

        zip_path.unlink(missing_ok=True)
        return target_dir

    def get_java(self, version: int, callback: ProgressCallback | None = None) -> Path:
        target_dir = self.runtime_dir() / f"java{version}"
        java_path = self._find_javaw(target_dir)
        if java_path:
            return java_path

        install_path = self.download_java(version, callback)
        java_path = self._find_javaw(install_path)
        if not java_path:
            raise RuntimeError("La instalacion de Java ha fallado")
        return java_path

    def installed_version_ids(self) -> set[str]:
        versions = minecraft_launcher_lib.utils.get_installed_versions(str(self.mc_dir))
        return {version["id"] for version in versions}

    def install_vanilla(self, version: str, callback: dict[str, Callable]) -> None:
        minecraft_launcher_lib.install.install_minecraft_version(
            version,
            str(self.mc_dir),
            callback=callback,
        )

    def find_forge_version(self, mc_version: str) -> str:
        forge_version = minecraft_launcher_lib.forge.find_forge_version(mc_version)
        if not forge_version:
            raise RuntimeError(f"No hay Forge compatible con Minecraft {mc_version}")
        return forge_version

    def install_forge(self, mc_version: str, java_path: Path, callback: dict[str, Callable]) -> str:
        forge_version = self.find_forge_version(mc_version)
        version_id = minecraft_launcher_lib.forge.forge_to_installed_version(forge_version)
        if version_id not in self.installed_version_ids():
            minecraft_launcher_lib.forge.install_forge_version(
                forge_version,
                str(self.mc_dir),
                callback=callback,
                java=str(java_path),
            )
        return version_id

    def launch(
        self,
        version: str,
        account_options: dict[str, str],
        mode: str,
        ram: int,
        game_options: dict[str, str | bool] | None = None,
        callback: ProgressCallback | None = None,
    ) -> subprocess.Popen:
        self._cancel = False
        reporter = ProgressReporter(callback)
        reporter.set_status("Preparando instalacion")

        is_forge = mode != "vanilla"
        java_version = self.required_java(version, is_forge)
        java_path = self.get_java(java_version, callback)

        if self._cancel:
            raise RuntimeError("Operacion cancelada")

        if mode == "vanilla":
            self.install_vanilla(version, reporter.as_dict())
            version_id = version
        else:
            version_id = self.install_forge(version, java_path, reporter.as_dict())

        if self._cancel:
            raise RuntimeError("Operacion cancelada")

        options = {
            **account_options,
            "executablePath": str(java_path),
            "launcherName": "N3mesisLauncher",
            "launcherVersion": "2.0",
            "gameDirectory": str(self.mc_dir),
            "jvmArguments": [
                f"-Xms{max(1, min(ram, 2))}G",
                f"-Xmx{ram}G",
                "-XX:+UseG1GC",
                "-XX:+UnlockExperimentalVMOptions",
                "-XX:G1NewSizePercent=20",
                "-XX:G1ReservePercent=20",
                "-Dfile.encoding=UTF-8",
            ],
        }
        if game_options:
            options.update(game_options)

        reporter.set_status("Iniciando Minecraft")
        cmd = minecraft_launcher_lib.command.get_minecraft_command(
            version_id,
            str(self.mc_dir),
            options,
        )

        self.process = subprocess.Popen(cmd, cwd=str(self.mc_dir))
        return self.process
