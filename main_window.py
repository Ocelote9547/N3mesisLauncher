import json
import os
import shutil

import minecraft_launcher_lib
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSlider,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from auth import DEFAULT_REDIRECT_URI, AuthManager
from curseforge import CurseForgeClient
from paths import config_path, launcher_dir, minecraft_dir, resource_path


FALLBACK_VERSIONS = [
    "1.21.4", "1.21.1", "1.20.6", "1.20.4", "1.20.1",
    "1.19.4", "1.19.2", "1.18.2", "1.17.1", "1.16.5",
    "1.15.2", "1.14.4", "1.13.2", "1.12.2", "1.8.9",
]
RAM_VALUES = [2, 4, 6, 8, 12, 16]
RESOLUTIONS = ["1280x720", "1600x900", "1920x1080", "2560x1440"]


class LaunchWorker(QThread):
    progress = pyqtSignal(str, int, int)
    failed = pyqtSignal(str)
    finished_ok = pyqtSignal()

    def __init__(
        self,
        core,
        auth: AuthManager,
        account_mode: str,
        username: str,
        version: str,
        mode: str,
        ram: int,
        game_options: dict[str, str | bool],
    ):
        super().__init__()
        self.core = core
        self.auth = auth
        self.account_mode = account_mode
        self.username = username
        self.version = version
        self.mode = mode
        self.ram = ram
        self.game_options = game_options

    def run(self) -> None:
        try:
            if self.account_mode == "microsoft":
                account = self.auth.microsoft_options()
                if not account:
                    raise RuntimeError("Conecta una cuenta Microsoft o cambia a modo offline.")
            else:
                account = self.auth.offline_options(self.username)

            self.core.launch(
                self.version,
                account,
                self.mode,
                self.ram,
                self.game_options,
                lambda status, current, total: self.progress.emit(status, current, total),
            )
            self.finished_ok.emit()
        except Exception as exc:
            self.failed.emit(str(exc))


class VersionFetchWorker(QThread):
    loaded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(self, mc_dir):
        super().__init__()
        self.mc_dir = mc_dir

    def run(self) -> None:
        try:
            versions = minecraft_launcher_lib.utils.get_available_versions(str(self.mc_dir))
            releases = [item["id"] for item in versions if item.get("type") == "release"]
            self.loaded.emit(releases or FALLBACK_VERSIONS)
        except Exception as exc:
            self.failed.emit(str(exc))


class CurseForgeWorker(QThread):
    loaded = pyqtSignal(list)
    installed = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, api_key: str, action: str, payload: dict, mc_dir):
        super().__init__()
        self.api_key = api_key
        self.action = action
        self.payload = payload
        self.mc_dir = mc_dir

    def run(self) -> None:
        try:
            client = CurseForgeClient(self.api_key)
            if self.action == "search":
                results = client.search(
                    self.payload.get("query", ""),
                    self.payload.get("version", ""),
                    self.payload.get("loader", "any"),
                    self.payload.get("type", "mod"),
                )
                self.loaded.emit(results)
                return

            if self.payload.get("type") == "modpack":
                count = client.install_modpack(
                    self.payload["project"],
                    self.payload.get("version", ""),
                    self.mc_dir,
                    self.mc_dir / "launcher" / "downloads",
                )
                self.installed.emit(f"Modpack instalado. Mods descargados: {count}")
            else:
                path = client.install_mod(
                    self.payload["project"],
                    self.payload.get("version", ""),
                    self.mc_dir / "mods",
                )
                self.installed.emit(f"Mod instalado: {path.name}")
        except Exception as exc:
            self.failed.emit(str(exc))


class MicrosoftLoginWorker(QThread):
    logged_in = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(
        self,
        auth: AuthManager,
        client_id: str,
        redirect_uri: str,
        final_url: str,
        state: str,
        verifier: str,
    ):
        super().__init__()
        self.auth = auth
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.final_url = final_url
        self.state = state
        self.verifier = verifier

    def run(self) -> None:
        try:
            account = self.auth.complete_login(
                self.client_id,
                self.redirect_uri,
                self.final_url,
                self.state,
                self.verifier,
            )
            self.logged_in.emit(account)
        except Exception as exc:
            self.failed.emit(str(exc))


class MicrosoftLoginDialog(QDialog):
    logged_in = pyqtSignal(dict)

    def __init__(self, auth: AuthManager, parent=None):
        super().__init__(parent)
        self.auth = auth
        self.state = ""
        self.verifier = ""
        self.worker: MicrosoftLoginWorker | None = None

        self.setWindowTitle("Cuenta Microsoft")
        self.setMinimumWidth(620)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        title = QLabel("Cuenta Microsoft")
        title.setObjectName("Title")

        hint = QLabel(
            "Genera el enlace, inicia sesion y pega la URL final. "
            "Hace falta un Azure Client ID configurado como cliente publico."
        )
        hint.setWordWrap(True)
        hint.setObjectName("Muted")

        self.client_id = QLineEdit()
        self.client_id.setPlaceholderText("Azure Client ID")
        self.client_id.setText(self.auth.config.get("microsoft_client_id", ""))

        self.redirect_uri = QLineEdit()
        self.redirect_uri.setPlaceholderText("Redirect URI")
        self.redirect_uri.setText(self.auth.config.get("microsoft_redirect_uri", DEFAULT_REDIRECT_URI))

        self.login_url = QTextEdit()
        self.login_url.setReadOnly(True)
        self.login_url.setFixedHeight(92)
        self.login_url.setPlaceholderText("Pulsa generar enlace")

        self.final_url = QLineEdit()
        self.final_url.setPlaceholderText("URL final despues del login")

        generate = QPushButton("Generar")
        generate.clicked.connect(self.generate_url)

        open_link = QPushButton("Abrir")
        open_link.clicked.connect(self.open_url)

        complete = QPushButton("Guardar")
        complete.setObjectName("PrimaryButton")
        complete.clicked.connect(self.complete_login)

        row = QHBoxLayout()
        row.addWidget(generate)
        row.addWidget(open_link)
        row.addStretch()
        row.addWidget(complete)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.client_id)
        layout.addWidget(self.redirect_uri)
        layout.addWidget(self.login_url)
        layout.addWidget(self.final_url)
        layout.addLayout(row)

    def generate_url(self) -> None:
        client_id = self.client_id.text().strip()
        redirect_uri = self.redirect_uri.text().strip() or DEFAULT_REDIRECT_URI
        if not client_id:
            QMessageBox.warning(self, "Falta Client ID", "Introduce el Client ID de Azure.")
            return
        url, self.state, self.verifier = self.auth.create_login_url(client_id, redirect_uri)
        self.login_url.setPlainText(url)

    def open_url(self) -> None:
        url = self.login_url.toPlainText().strip()
        if not url:
            self.generate_url()
            url = self.login_url.toPlainText().strip()
        if url:
            os.startfile(url)

    def complete_login(self) -> None:
        if not self.state or not self.verifier:
            QMessageBox.warning(self, "Genera el enlace", "Primero genera el enlace de inicio de sesion.")
            return
        final_url = self.final_url.text().strip()
        if not final_url:
            QMessageBox.warning(self, "Falta URL", "Pega la URL final despues de iniciar sesion.")
            return

        self.setEnabled(False)
        self.worker = MicrosoftLoginWorker(
            self.auth,
            self.client_id.text().strip(),
            self.redirect_uri.text().strip() or DEFAULT_REDIRECT_URI,
            final_url,
            self.state,
            self.verifier,
        )
        self.worker.logged_in.connect(self.on_logged_in)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_logged_in(self, account: dict) -> None:
        self.logged_in.emit(account)
        self.accept()

    def on_failed(self, message: str) -> None:
        self.setEnabled(True)
        QMessageBox.critical(self, "No se pudo iniciar sesion", message)


class MainWindow(QWidget):
    def __init__(self, core):
        super().__init__()
        self.core = core
        self.mc_dir = minecraft_dir()
        self.launcher_home = launcher_dir(self.mc_dir)
        self.config_file = config_path(self.mc_dir)
        self.config: dict = {}
        self.auth: AuthManager | None = None
        self.worker: LaunchWorker | None = None
        self.version_worker: VersionFetchWorker | None = None
        self.curseforge_worker: CurseForgeWorker | None = None
        self.curseforge_results: list[dict] = []
        self.versions = FALLBACK_VERSIONS[:]
        self.bg = QPixmap(str(resource_path("background.jpg")))
        self.scaled_bg = QPixmap()
        self.logo = QPixmap(str(resource_path("icon.ico")))

        self.setWindowTitle("N3mesis Launcher")
        icon_path = resource_path("icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1180, 720)
        self.setMinimumSize(980, 620)

        self.load_config()
        self.auth = AuthManager(self.config, self.config_file)
        self.init_ui()
        self.apply_config()
        self.populate_versions()
        self.refresh_mods()
        self.refresh_java_status()
        self.refresh_skin_preview()
        self.update_account_state()
        self.update_profile()

    def load_config(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        if self.config_file.exists():
            try:
                with self.config_file.open("r", encoding="utf-8") as f:
                    self.config = json.load(f)
            except (OSError, json.JSONDecodeError):
                self.config = {}

    def save_config(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with self.config_file.open("w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

    def init_ui(self) -> None:
        self.setStyleSheet("""
            QWidget {
                color: #f4f7fb;
                font-family: Bahnschrift, Segoe UI Variable, Segoe UI;
                font-size: 14px;
            }
            QLabel { background: transparent; }
            QLabel#Brand {
                font-size: 29px;
                font-weight: 900;
                letter-spacing: 0px;
            }
            QLabel#Title {
                font-size: 30px;
                font-weight: 900;
                letter-spacing: 0px;
            }
            QLabel#SubTitle {
                color: rgba(244,247,251,175);
                font-size: 15px;
            }
            QLabel#Muted, QLabel#Status, QLabel#Small {
                color: rgba(244,247,251,150);
            }
            QLabel#Avatar {
                background-color: #dbe9ff;
                color: #07101f;
                border-radius: 8px;
                font-size: 30px;
                font-weight: 900;
            }
            QLabel#SkinPreview {
                background-color: rgba(7, 12, 24, 205);
                border: 1px solid rgba(70, 124, 198, 120);
                border-radius: 8px;
            }
            QFrame#Sidebar {
                background-color: rgba(3, 6, 13, 232);
                border: 1px solid rgba(98, 144, 205, 62);
                border-radius: 8px;
            }
            QFrame#GlowPanel {
                background-color: rgba(5, 9, 18, 232);
                border: 1px solid rgba(70, 124, 198, 120);
                border-radius: 8px;
            }
            QFrame#SoftPanel {
                background-color: rgba(7, 12, 24, 205);
                border: 1px solid rgba(255,255,255,26);
                border-radius: 8px;
            }
            QLineEdit, QComboBox, QTextEdit, QListWidget {
                background-color: rgba(2, 5, 11, 185);
                border: 1px solid rgba(91, 132, 190, 70);
                border-radius: 6px;
                padding: 10px;
                selection-background-color: #284f86;
            }
            QLineEdit:focus, QComboBox:focus, QTextEdit:focus {
                border-color: rgba(150, 190, 255, 190);
            }
            QComboBox::drop-down {
                border: 0;
                width: 28px;
            }
            QPushButton {
                background-color: rgba(9, 18, 34, 210);
                border: 1px solid rgba(91, 132, 190, 82);
                border-radius: 6px;
                padding: 10px 14px;
                font-weight: 800;
            }
            QPushButton:hover {
                background-color: rgba(17, 34, 62, 225);
                border-color: rgba(170, 205, 255, 170);
            }
            QPushButton:checked {
                background-color: rgba(22, 43, 78, 240);
                border-color: rgba(202, 223, 255, 210);
            }
            QPushButton#NavButton {
                text-align: left;
                padding: 12px 14px;
                background-color: transparent;
                border-color: transparent;
            }
            QPushButton#NavButton:checked {
                background-color: rgba(13, 31, 60, 230);
                border-color: rgba(120, 172, 238, 155);
            }
            QPushButton#PrimaryButton {
                background-color: #dbe9ff;
                border: 1px solid #ffffff;
                color: #050a14;
                font-size: 18px;
            }
            QPushButton#DangerButton {
                background-color: rgba(88, 24, 34, 220);
                border-color: rgba(255, 145, 160, 130);
            }
            QPushButton#GhostButton {
                background-color: rgba(255,255,255,8);
            }
            QPushButton:disabled {
                color: rgba(255,255,255,80);
                background-color: rgba(255,255,255,8);
                border-color: rgba(255,255,255,16);
            }
            QCheckBox {
                spacing: 9px;
                color: rgba(244,247,251,205);
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid rgba(120, 172, 238, 100);
                background: rgba(2, 5, 11, 210);
            }
            QCheckBox::indicator:checked {
                background: #dbe9ff;
                border-color: white;
            }
            QProgressBar {
                background-color: rgba(2, 5, 11, 190);
                border: 1px solid rgba(91, 132, 190, 70);
                border-radius: 5px;
                height: 12px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #dbe9ff;
                border-radius: 4px;
            }
            QSlider::groove:horizontal {
                height: 7px;
                background: rgba(255,255,255,22);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 20px;
                height: 20px;
                margin: -7px 0;
                border-radius: 10px;
                background: #dbe9ff;
            }
        """)

        root = QGridLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setHorizontalSpacing(22)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(212)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(18, 18, 18, 18)
        side.setSpacing(10)

        brand = QLabel("N3MESIS")
        brand.setObjectName("Brand")
        build = QLabel("Launcher")
        build.setObjectName("Muted")

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_play = self.nav_button("Play", 0)
        self.nav_mods = self.nav_button("Mods", 1)
        self.nav_settings = self.nav_button("Ajustes", 2)
        self.nav_play.setChecked(True)

        self.account_state = QLabel()
        self.account_state.setObjectName("Muted")
        self.account_state.setWordWrap(True)

        side.addWidget(brand)
        side.addWidget(build)
        side.addSpacing(22)
        side.addWidget(self.nav_play)
        side.addWidget(self.nav_mods)
        side.addWidget(self.nav_settings)
        side.addStretch()
        side.addWidget(self.account_state)

        self.pages = QStackedWidget()
        self.pages.addWidget(self.build_play_page())
        self.pages.addWidget(self.build_mods_page())
        self.pages.addWidget(self.build_settings_page())
        self.nav_group.idClicked.connect(self.pages.setCurrentIndex)

        root.addWidget(sidebar, 0, 0)
        root.addWidget(self.pages, 0, 1)
        root.setColumnStretch(1, 1)

    def nav_button(self, text: str, page_id: int) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("NavButton")
        button.setCheckable(True)
        self.nav_group.addButton(button, page_id)
        return button

    def panel(self, object_name: str = "GlowPanel") -> QFrame:
        frame = QFrame()
        frame.setObjectName(object_name)
        if object_name == "GlowPanel":
            glow = QGraphicsDropShadowEffect(frame)
            glow.setBlurRadius(26)
            glow.setOffset(0, 0)
            glow.setColor(QColor(58, 103, 168, 150))
            frame.setGraphicsEffect(glow)
        return frame

    def build_play_page(self) -> QWidget:
        page = QWidget()
        root = QGridLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setHorizontalSpacing(22)

        left = QVBoxLayout()
        left.setSpacing(18)

        hero = self.panel("SoftPanel")
        hero_layout = QGridLayout(hero)
        hero_layout.setContentsMargins(24, 24, 24, 24)
        hero_layout.setHorizontalSpacing(18)

        title = QLabel("N3mesis Client")
        title.setObjectName("Title")
        subtitle = QLabel("Oscuro, limpio y rapido. Elige perfil, version y entra.")
        subtitle.setObjectName("SubTitle")
        subtitle.setWordWrap(True)

        self.avatar = QLabel("N")
        self.avatar.setObjectName("Avatar")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFixedSize(74, 74)
        if not self.logo.isNull():
            self.avatar.setPixmap(
                self.logo.scaled(
                    54,
                    54,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        self.profile_name = QLabel("Player")
        self.profile_name.setObjectName("Title")
        self.profile_meta = QLabel("Offline")
        self.profile_meta.setObjectName("Muted")

        profile_box = QVBoxLayout()
        profile_box.addWidget(self.profile_name)
        profile_box.addWidget(self.profile_meta)

        hero_layout.addWidget(title, 0, 0, 1, 2)
        hero_layout.addWidget(subtitle, 1, 0, 1, 2)
        hero_layout.addWidget(self.avatar, 0, 2, 2, 1)
        hero_layout.addLayout(profile_box, 0, 3, 2, 1)
        hero_layout.setColumnStretch(1, 1)

        left.addWidget(hero)
        left.addStretch(1)

        launch_panel = self.panel("GlowPanel")
        launch_panel.setFixedWidth(390)
        form = QVBoxLayout(launch_panel)
        form.setContentsMargins(22, 22, 22, 22)
        form.setSpacing(13)

        form_title = QLabel("Lanzar juego")
        form_title.setObjectName("Title")

        self.username = QComboBox()
        self.username.setEditable(True)
        self.username.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.username.setPlaceholderText("Nombre offline")
        self.username.currentTextChanged.connect(self.update_profile)

        self.account_group = QButtonGroup(self)
        self.offline_button = QPushButton("Offline")
        self.offline_button.setCheckable(True)
        self.microsoft_button = QPushButton("Microsoft")
        self.microsoft_button.setCheckable(True)
        self.account_group.addButton(self.offline_button)
        self.account_group.addButton(self.microsoft_button)
        self.offline_button.clicked.connect(self.on_account_mode_changed)
        self.microsoft_button.clicked.connect(self.on_account_mode_changed)

        account_row = QHBoxLayout()
        account_row.addWidget(self.offline_button)
        account_row.addWidget(self.microsoft_button)

        self.login_button = QPushButton("Conectar")
        self.login_button.clicked.connect(self.open_microsoft_login)
        self.logout_button = QPushButton("Quitar")
        self.logout_button.setObjectName("GhostButton")
        self.logout_button.clicked.connect(self.logout_microsoft)

        login_row = QHBoxLayout()
        login_row.addWidget(self.login_button)
        login_row.addWidget(self.logout_button)

        self.version = QComboBox()
        self.version.currentTextChanged.connect(self.update_profile)
        self.refresh_versions = QPushButton("Actualizar versiones")
        self.refresh_versions.setObjectName("GhostButton")
        self.refresh_versions.clicked.connect(self.fetch_versions)

        self.mode = QComboBox()
        self.mode.addItems(["vanilla", "forge"])
        self.mode.currentTextChanged.connect(self.update_profile)

        self.ram_label = QLabel()
        self.ram = QSlider(Qt.Orientation.Horizontal)
        self.ram.setMinimum(0)
        self.ram.setMaximum(len(RAM_VALUES) - 1)
        self.ram.setTickInterval(1)
        self.ram.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.ram.valueChanged.connect(self.update_ram_label)

        self.server = QLineEdit()
        self.server.setPlaceholderText("Servidor opcional")

        self.fullscreen = QCheckBox("Pantalla completa")

        self.status = QLabel("Listo")
        self.status.setObjectName("Status")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setVisible(False)

        self.play = QPushButton("PLAY")
        self.play.setObjectName("PrimaryButton")
        self.play.setFixedHeight(58)
        self.play.clicked.connect(self.launch)

        self.cancel = QPushButton("CANCELAR")
        self.cancel.setObjectName("DangerButton")
        self.cancel.setFixedHeight(44)
        self.cancel.setVisible(False)
        self.cancel.clicked.connect(self.cancel_launch)

        form.addWidget(form_title)
        form.addWidget(self.username)
        form.addLayout(account_row)
        form.addLayout(login_row)
        form.addWidget(self.version)
        form.addWidget(self.refresh_versions)
        form.addWidget(self.mode)
        form.addWidget(self.ram_label)
        form.addWidget(self.ram)
        form.addWidget(self.server)
        form.addWidget(self.fullscreen)
        form.addStretch()
        form.addWidget(self.status)
        form.addWidget(self.progress)
        form.addWidget(self.play)
        form.addWidget(self.cancel)

        root.addLayout(left, 0, 0)
        root.addWidget(launch_panel, 0, 1)
        root.setColumnStretch(0, 1)
        return page

    def build_mods_page(self) -> QWidget:
        page = QWidget()
        root = QGridLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setHorizontalSpacing(18)

        panel = self.panel("GlowPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        title = QLabel("CurseForge")
        title.setObjectName("Title")
        hint = QLabel("Busca mods o modpacks de Minecraft. Necesitas una API key de CurseForge en Ajustes.")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)

        search_row = QHBoxLayout()
        self.cf_search = QLineEdit()
        self.cf_search.setPlaceholderText("Buscar, ej. sodium, jei, better mc...")
        self.cf_type = QComboBox()
        self.cf_type.addItems(["mod", "modpack"])
        self.cf_loader = QComboBox()
        self.cf_loader.addItems(["any", "forge", "fabric", "quilt", "neoforge"])
        search_button = QPushButton("Buscar")
        search_button.clicked.connect(self.search_curseforge)
        search_row.addWidget(self.cf_search, 2)
        search_row.addWidget(self.cf_type)
        search_row.addWidget(self.cf_loader)
        search_row.addWidget(search_button)

        self.cf_results = QListWidget()
        install_selected = QPushButton("Instalar seleccionado")
        install_selected.clicked.connect(self.install_curseforge_selected)

        self.mods_list = QListWidget()

        add_mod = QPushButton("Instalar .jar local")
        add_mod.clicked.connect(self.install_mod)
        open_mods = QPushButton("Abrir carpeta mods")
        open_mods.setObjectName("GhostButton")
        open_mods.clicked.connect(self.open_mods_folder)
        refresh = QPushButton("Refrescar")
        refresh.setObjectName("GhostButton")
        refresh.clicked.connect(self.refresh_mods)

        row = QHBoxLayout()
        row.addWidget(install_selected)
        row.addWidget(add_mod)
        row.addWidget(open_mods)
        row.addWidget(refresh)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(search_row)
        layout.addWidget(self.cf_results, 2)
        layout.addLayout(row)
        layout.addWidget(QLabel("Mods locales"))
        layout.addWidget(self.mods_list, 1)
        root.addWidget(panel, 0, 0)
        return page

    def build_skins_page(self) -> QWidget:
        page = QWidget()
        root = QGridLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setHorizontalSpacing(18)

        panel = self.panel("GlowPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        title = QLabel("Skins")
        title.setObjectName("Title")
        hint = QLabel(
            "Microsoft usa la skin oficial de la cuenta. En offline Minecraft vanilla no aplica skins externas; "
            "aqui se guarda una skin de perfil para el launcher y queda preparado para integrarlo con un mod de skins."
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)

        self.skin_preview = QLabel("Sin skin")
        self.skin_preview.setObjectName("SkinPreview")
        self.skin_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.skin_preview.setFixedSize(220, 220)
        glow = QGraphicsDropShadowEffect(self.skin_preview)
        glow.setBlurRadius(22)
        glow.setOffset(0, 0)
        glow.setColor(QColor(58, 103, 168, 130))
        self.skin_preview.setGraphicsEffect(glow)

        choose = QPushButton("Elegir skin PNG")
        choose.clicked.connect(self.choose_skin)
        clear = QPushButton("Quitar skin")
        clear.setObjectName("GhostButton")
        clear.clicked.connect(self.clear_skin)

        row = QHBoxLayout()
        row.addWidget(choose)
        row.addWidget(clear)
        row.addStretch()

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.skin_preview, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(row)
        layout.addStretch()
        root.addWidget(panel, 0, 0)
        return page

    def build_settings_page(self) -> QWidget:
        page = QWidget()
        root = QGridLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setHorizontalSpacing(18)

        panel = self.panel("GlowPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(12)

        title = QLabel("Ajustes")
        title.setObjectName("Title")

        self.java_status = QLabel()
        self.java_status.setObjectName("Muted")
        self.java_status.setWordWrap(True)

        open_mc = QPushButton("Abrir .minecraft")
        open_mc.clicked.connect(self.open_mc)
        open_runtime = QPushButton("Abrir runtime N3mesis")
        open_runtime.setObjectName("GhostButton")
        open_runtime.clicked.connect(self.open_runtime_folder)
        refresh_java = QPushButton("Revisar Java")
        refresh_java.setObjectName("GhostButton")
        refresh_java.clicked.connect(self.refresh_java_status)

        row = QHBoxLayout()
        row.addWidget(open_mc)
        row.addWidget(open_runtime)
        row.addWidget(refresh_java)
        row.addStretch()

        layout.addWidget(title)
        layout.addWidget(self.java_status)
        layout.addLayout(row)
        layout.addStretch()
        root.addWidget(panel, 0, 0)
        return page

    def apply_config(self) -> None:
        history = self.config.get("username_history", [])
        current_name = self.config.get("username", "")
        names = []
        for name in [current_name, *history]:
            if name and name not in names:
                names.append(name)
        self.username.addItems(names)
        self.username.setCurrentText(current_name)

        self.set_combo_value(self.mode, self.config.get("last_mode", "vanilla"))
        self.server.setText(self.config.get("server", ""))
        self.fullscreen.setChecked(bool(self.config.get("fullscreen", False)))

        ram = self.config.get("ram", 4)
        self.ram.setValue(RAM_VALUES.index(ram) if ram in RAM_VALUES else 1)
        account_mode = self.config.get("account_mode", "offline")
        self.microsoft_button.setChecked(account_mode == "microsoft")
        self.offline_button.setChecked(account_mode != "microsoft")
        self.update_ram_label(self.ram.value())

    def set_combo_value(self, combo: QComboBox, value: str) -> None:
        index = combo.findText(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def populate_versions(self) -> None:
        current = self.version.currentText() or self.config.get("last_version", "1.20.1")
        self.version.blockSignals(True)
        self.version.clear()
        self.version.addItems(self.versions)
        self.set_combo_value(self.version, current)
        self.version.blockSignals(False)
        self.update_profile()

    def fetch_versions(self) -> None:
        self.refresh_versions.setEnabled(False)
        self.refresh_versions.setText("Cargando...")
        self.version_worker = VersionFetchWorker(self.mc_dir)
        self.version_worker.loaded.connect(self.on_versions_loaded)
        self.version_worker.failed.connect(self.on_versions_failed)
        self.version_worker.start()

    def on_versions_loaded(self, versions: list) -> None:
        self.versions = versions
        self.refresh_versions.setEnabled(True)
        self.refresh_versions.setText("Actualizar versiones")
        self.populate_versions()
        self.status.setText(f"{len(versions)} versiones cargadas")

    def on_versions_failed(self, message: str) -> None:
        self.refresh_versions.setEnabled(True)
        self.refresh_versions.setText("Actualizar versiones")
        QMessageBox.warning(self, "Versiones", f"No se pudieron cargar versiones: {message}")

    def update_ram_label(self, index: int) -> None:
        self.ram_label.setText(f"RAM asignada: {RAM_VALUES[index]} GB")

    def update_profile(self, *args) -> None:
        name = self.username.currentText().strip() or "Player"
        mode = self.mode.currentText() if hasattr(self, "mode") else "vanilla"
        version = self.version.currentText() if hasattr(self, "version") else "1.20.1"
        self.profile_name.setText(name)
        self.profile_meta.setText(f"{mode.upper()} / {version}")
        if self.logo.isNull():
            self.avatar.setText(name[:1].upper())

    def on_account_mode_changed(self) -> None:
        self.config["account_mode"] = "microsoft" if self.microsoft_button.isChecked() else "offline"
        self.save_config()
        self.update_account_state()
        self.update_profile()

    def update_account_state(self) -> None:
        account = self.config.get("microsoft_account")
        if account:
            self.account_state.setText(f"Microsoft\n{account.get('name', 'cuenta guardada')}")
            self.logout_button.setEnabled(True)
        else:
            self.account_state.setText("Offline listo\nMicrosoft sin conectar")
            self.logout_button.setEnabled(False)
        self.username.setEnabled(self.offline_button.isChecked())
        self.login_button.setEnabled(self.microsoft_button.isChecked())

    def open_microsoft_login(self) -> None:
        dialog = MicrosoftLoginDialog(self.auth, self)
        dialog.logged_in.connect(self.on_microsoft_logged_in)
        dialog.exec()

    def on_microsoft_logged_in(self, account: dict) -> None:
        self.username.setCurrentText(account.get("name", ""))
        self.microsoft_button.setChecked(True)
        self.update_account_state()
        self.update_profile()

    def logout_microsoft(self) -> None:
        self.auth.logout_microsoft()
        self.offline_button.setChecked(True)
        self.update_account_state()

    def open_mc(self) -> None:
        self.mc_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(self.mc_dir))

    def open_runtime_folder(self) -> None:
        path = self.core.runtime_dir()
        os.startfile(str(path))

    def mods_dir(self):
        path = self.mc_dir / "mods"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def refresh_mods(self) -> None:
        if not hasattr(self, "mods_list"):
            return
        self.mods_list.clear()
        for mod in sorted(self.mods_dir().glob("*.jar")):
            self.mods_list.addItem(mod.name)
        if self.mods_list.count() == 0:
            self.mods_list.addItem("No hay mods instalados")

    def install_mod(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "Seleccionar mods", "", "Minecraft mods (*.jar)")
        if not files:
            return
        target = self.mods_dir()
        for file_name in files:
            source = os.path.abspath(file_name)
            shutil.copy2(source, target / os.path.basename(source))
        self.refresh_mods()

    def open_mods_folder(self) -> None:
        os.startfile(str(self.mods_dir()))

    def skins_dir(self):
        path = self.launcher_home / "skins"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def choose_skin(self) -> None:
        file_name, _ = QFileDialog.getOpenFileName(self, "Seleccionar skin", "", "Minecraft skin (*.png)")
        if not file_name:
            return
        target = self.skins_dir() / os.path.basename(file_name)
        shutil.copy2(os.path.abspath(file_name), target)
        self.config["profile_skin"] = str(target)
        self.save_config()
        self.refresh_skin_preview()

    def clear_skin(self) -> None:
        self.config.pop("profile_skin", None)
        self.save_config()
        self.refresh_skin_preview()

    def refresh_skin_preview(self) -> None:
        if not hasattr(self, "skin_preview"):
            return
        skin_path = self.config.get("profile_skin", "")
        pixmap = QPixmap(skin_path)
        if skin_path and not pixmap.isNull():
            self.skin_preview.setText("")
            self.skin_preview.setPixmap(
                pixmap.scaled(
                    196,
                    196,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.FastTransformation,
                )
            )
        else:
            self.skin_preview.setPixmap(QPixmap())
            self.skin_preview.setText("Sin skin")

    def refresh_java_status(self) -> None:
        if not hasattr(self, "java_status"):
            return
        installations = self.core.java_installations()
        if not installations:
            self.java_status.setText(
                "No se ha detectado Java local todavia. El launcher descargara Java 8, 17 o 21 automaticamente segun la version elegida."
            )
            return
        lines = ["Java detectado:"]
        for item in installations:
            lines.append(f"{item['name']} - {item['source']}\n{item['path']}")
        self.java_status.setText("\n\n".join(lines))

    def can_launch_with_selected_account(self) -> bool:
        if self.microsoft_button.isChecked():
            if self.config.get("microsoft_account"):
                return True
            QMessageBox.warning(
                self,
                "Microsoft no conectado",
                "Conecta una cuenta Microsoft o cambia a modo offline.",
            )
            return False
        return True

    def save_username_history(self, username: str) -> None:
        if not username:
            return
        history = self.config.get("username_history", [])
        history = [name for name in history if name != username]
        history.insert(0, username)
        self.config["username_history"] = history[:8]
        if self.username.findText(username) < 0:
            self.username.insertItem(0, username)

    def selected_game_options(self) -> dict[str, str | bool]:
        options: dict[str, str | bool] = {}
        server = self.server.text().strip()
        if server:
            if ":" in server:
                host, port = server.rsplit(":", 1)
                options["server"] = host
                if port.isdigit():
                    options["port"] = port
            else:
                options["server"] = server
        if self.fullscreen.isChecked():
            options["fullscreen"] = True
        return options

    def launch(self) -> None:
        if not self.can_launch_with_selected_account():
            return

        version = self.version.currentText()
        mode = self.mode.currentText()
        ram = RAM_VALUES[self.ram.value()]
        username = self.username.currentText().strip() or "Player"
        account_mode = "microsoft" if self.microsoft_button.isChecked() else "offline"

        self.config["username"] = username
        self.config["last_version"] = version
        self.config["last_mode"] = mode
        self.config["ram"] = ram
        self.config["account_mode"] = account_mode
        self.config["server"] = self.server.text().strip()
        self.config["fullscreen"] = self.fullscreen.isChecked()
        self.save_username_history(username)
        self.save_config()

        self.set_busy(True)
        self.worker = LaunchWorker(
            self.core,
            self.auth,
            account_mode,
            username,
            version,
            mode,
            ram,
            self.selected_game_options(),
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.failed.connect(self.launch_failed)
        self.worker.finished_ok.connect(self.launch_finished)
        self.worker.start()

    def set_busy(self, busy: bool) -> None:
        self.play.setVisible(not busy)
        self.cancel.setVisible(busy)
        self.progress.setVisible(busy)
        self.version.setEnabled(not busy)
        self.mode.setEnabled(not busy)
        self.ram.setEnabled(not busy)
        self.username.setEnabled(not busy and self.offline_button.isChecked())
        self.login_button.setEnabled(not busy and self.microsoft_button.isChecked())
        self.offline_button.setEnabled(not busy)
        self.microsoft_button.setEnabled(not busy)
        self.refresh_versions.setEnabled(not busy)
        if busy:
            self.progress.setValue(0)
            self.status.setText("Preparando")
        else:
            self.progress.setRange(0, 100)
            self.progress.setValue(0)

    def update_progress(self, status: str, current: int, total: int) -> None:
        self.status.setText(status)
        if total > 0:
            self.progress.setRange(0, 100)
            self.progress.setValue(min(100, int((current / total) * 100)))
        else:
            self.progress.setRange(0, 0)

    def launch_finished(self) -> None:
        self.status.setText("Minecraft iniciado")
        self.set_busy(False)

    def launch_failed(self, message: str) -> None:
        self.status.setText("Error")
        self.set_busy(False)
        if message != "Operacion cancelada":
            QMessageBox.critical(self, "No se pudo iniciar Minecraft", message)

    def cancel_launch(self) -> None:
        self.core.cancel()
        self.status.setText("Cancelando...")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self.bg.isNull():
            self.scaled_bg = self.bg.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(2, 4, 9))
        if not self.scaled_bg.isNull():
            painter.setOpacity(0.18)
            painter.drawPixmap(self.rect(), self.scaled_bg)
            painter.setOpacity(1)
        painter.fillRect(self.rect(), QColor(1, 4, 11, 178))
        painter.fillRect(0, 0, self.width(), self.height(), QColor(8, 22, 44, 54))

    def closeEvent(self, event) -> None:
        if self.worker and self.worker.isRunning():
            self.core.cancel()
            self.worker.wait(1500)
        if self.version_worker and self.version_worker.isRunning():
            self.version_worker.wait(1000)
        QApplication.restoreOverrideCursor()
        event.accept()
