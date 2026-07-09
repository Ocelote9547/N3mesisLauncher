import json
from pathlib import Path
from typing import Any

import minecraft_launcher_lib


DEFAULT_REDIRECT_URI = "http://localhost"


class AuthManager:
    def __init__(self, config: dict[str, Any], config_path: Path):
        self.config = config
        self.config_path = config_path

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with self.config_path.open("w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

    def offline_options(self, username: str) -> dict[str, str]:
        clean_name = username.strip() or "Player"
        return {
            "username": clean_name,
            "uuid": "offline",
            "token": "0",
        }

    def microsoft_options(self) -> dict[str, str] | None:
        account = self.config.get("microsoft_account")
        if not account:
            return None

        client_id = self.config.get("microsoft_client_id", "").strip()
        refresh_token = account.get("refresh_token")
        if client_id and refresh_token:
            try:
                refreshed = minecraft_launcher_lib.microsoft_account.complete_refresh(
                    client_id,
                    None,
                    self.config.get("microsoft_redirect_uri") or DEFAULT_REDIRECT_URI,
                    refresh_token,
                )
                self.config["microsoft_account"] = refreshed
                self.config["username"] = refreshed["name"]
                self.save()
                account = refreshed
            except Exception:
                pass

        if not account.get("access_token"):
            return None

        return {
            "username": account.get("name", "Player"),
            "uuid": account.get("id", "offline"),
            "token": account["access_token"],
        }

    def create_login_url(self, client_id: str, redirect_uri: str) -> tuple[str, str, str]:
        return minecraft_launcher_lib.microsoft_account.get_secure_login_data(
            client_id,
            redirect_uri,
        )

    def complete_login(
        self,
        client_id: str,
        redirect_uri: str,
        final_url: str,
        state: str,
        code_verifier: str,
    ) -> dict[str, Any]:
        auth_code = minecraft_launcher_lib.microsoft_account.parse_auth_code_url(final_url, state)
        account = minecraft_launcher_lib.microsoft_account.complete_login(
            client_id,
            None,
            redirect_uri,
            auth_code,
            code_verifier,
        )
        self.config["microsoft_client_id"] = client_id
        self.config["microsoft_redirect_uri"] = redirect_uri
        self.config["microsoft_account"] = account
        self.config["username"] = account["name"]
        self.config["account_mode"] = "microsoft"
        self.save()
        return account

    def logout_microsoft(self) -> None:
        self.config.pop("microsoft_account", None)
        if self.config.get("account_mode") == "microsoft":
            self.config["account_mode"] = "offline"
        self.save()
