import json
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests


BASE_URL = "https://api.curseforge.com/v1"
MINECRAFT_GAME_ID = 432
CLASS_MODS = 6
CLASS_MODPACKS = 4471
MODLOADERS = {
    "any": None,
    "forge": 1,
    "fabric": 4,
    "quilt": 5,
    "neoforge": 6,
}


class CurseForgeClient:
    def __init__(self, api_key: str):
        self.api_key = api_key.strip()

    def headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("Configura una API key de CurseForge en Ajustes.")
        return {
            "Accept": "application/json",
            "x-api-key": self.api_key,
        }

    def get(self, path: str, params: dict | None = None) -> dict:
        response = requests.get(
            f"{BASE_URL}{path}",
            headers=self.headers(),
            params=params or {},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def search(self, query: str, version: str, loader: str, pack_type: str) -> list[dict]:
        params = {
            "gameId": MINECRAFT_GAME_ID,
            "classId": CLASS_MODPACKS if pack_type == "modpack" else CLASS_MODS,
            "searchFilter": query,
            "pageSize": 20,
            "sortField": 2,
            "sortOrder": "desc",
        }
        if version:
            params["gameVersion"] = version
        loader_type = MODLOADERS.get(loader)
        if loader_type:
            params["modLoaderType"] = loader_type
        return self.get("/mods/search", params).get("data", [])

    def file(self, mod_id: int, file_id: int) -> dict:
        return self.get(f"/mods/{mod_id}/files/{file_id}").get("data", {})

    def download_url(self, mod_id: int, file_id: int) -> str:
        data = self.get(f"/mods/{mod_id}/files/{file_id}/download-url")
        url = data.get("data")
        if not url:
            raise RuntimeError("CurseForge no permite descargar este archivo desde clientes externos.")
        return url

    def choose_file(self, mod: dict, version: str) -> dict:
        for file_info in mod.get("latestFilesIndexes", []):
            if version and file_info.get("gameVersion") != version:
                continue
            return self.file(mod["id"], file_info["fileId"])
        files = mod.get("latestFiles", [])
        if files:
            return files[0]
        raise RuntimeError("No hay archivo descargable para este proyecto.")

    def download_file(self, url: str, target_dir: Path) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        name = Path(urlparse(url).path).name or "curseforge-download.jar"
        target = target_dir / name
        with requests.get(url, stream=True, timeout=60) as response:
            response.raise_for_status()
            with target.open("wb") as f:
                for chunk in response.iter_content(1024 * 256):
                    if chunk:
                        f.write(chunk)
        return target

    def install_mod(self, mod: dict, version: str, mods_dir: Path) -> Path:
        file_info = self.choose_file(mod, version)
        url = file_info.get("downloadUrl") or self.download_url(mod["id"], file_info["id"])
        return self.download_file(url, mods_dir)

    def install_modpack(self, modpack: dict, version: str, minecraft_dir: Path, downloads_dir: Path) -> int:
        file_info = self.choose_file(modpack, version)
        url = file_info.get("downloadUrl") or self.download_url(modpack["id"], file_info["id"])
        archive_path = self.download_file(url, downloads_dir)

        installed = 0
        with zipfile.ZipFile(archive_path, "r") as pack_zip:
            manifest = json.loads(pack_zip.read("manifest.json").decode("utf-8"))
            overrides = manifest.get("overrides", "overrides")
            for member in pack_zip.namelist():
                if member.startswith(overrides + "/") and not member.endswith("/"):
                    relative = member[len(overrides) + 1:]
                    target = minecraft_dir / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with pack_zip.open(member) as src, target.open("wb") as dst:
                        shutil.copyfileobj(src, dst)

            mods_dir = minecraft_dir / "mods"
            mods_dir.mkdir(parents=True, exist_ok=True)
            for entry in manifest.get("files", []):
                mod_id = int(entry["projectID"])
                file_id = int(entry["fileID"])
                try:
                    file_url = self.download_url(mod_id, file_id)
                    self.download_file(file_url, mods_dir)
                    installed += 1
                except Exception:
                    continue
        return installed
