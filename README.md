# ✦ N3MESIS Launcher

![version](https://img.shields.io/badge/version-2.2.0-10b981)
![platform](https://img.shields.io/badge/Windows-10%2F11-0ea5e9)
![python](https://img.shields.io/badge/Python-3.13-3776AB)
![minecraft](https://img.shields.io/badge/Minecraft-Java_Edition-65a30d)

Launcher moderno, rápido y elegante para **Minecraft: Java Edition**, con instancias aisladas, todos los loaders, login Microsoft y tienda de mods integrada.

> **Descarga la última versión aquí: [Releases](../../releases/latest)** — solo necesitas el `.exe`, sin instalar Python ni Java.

---

## ✨ Características

**Jugar**
- Vanilla, **Forge, Fabric, Quilt y NeoForge** (con validación anti-crash: Forge/NeoForge solo en releases estables).
- **Instancias aisladas**: cada mundo con sus mods, saves, configs y RAM propios. Crear, duplicar (exportar/importar `.zip`), icono propio y auto-detección de carpetas.
- **Java automático**: descarga el Adoptium exacto (8/17/21) solo si falta, y lo reutiliza siempre.
- Servidor directo al entrar, pantalla completa y RAM configurable.

**Cuentas**
- **Offline** con multisesión (varios nombres) y UUIDs estables.
- **Microsoft** con flujo por código de dispositivo (multicuenta, reconexión y refresco automático de tokens).

**Complementos (Modrinth)**
- Buscador de **mods, resource packs, shaders, datapacks y modpacks** con populares al abrir.
- Selector de versión con loader y compatibilidad según tu Minecraft, instalación en 1 clic (los modpacks crean su propia instancia) y lista local con activar/desactivar, borrado en lote y detalles.

**Sistema**
- 🎨 Temas claro/oscuro + 6 acentos, fondo personalizable con atenuación.
- 🌍 9 idiomas con cambio instantáneo.
- 🖥️ Consola integrada, auto-actualizador desde GitHub, guía inicial y atajos (`Enter` = jugar, `Ctrl+R` = refrescar).

---

## ⬇️ Descarga e instalación

1. Ve a **[Releases](../../releases/latest)**.
2. Descarga `N3mesisLauncher.Vx.y.z.exe`.
3. Ejecútalo. Eso es todo: Java y Minecraft se descargan solos al darle a **JUGAR**.

> El código fuente de este repositorio es privado; aquí solo se publican el README y los instaladores.

---

## ▶️ Uso rápido

1. **Crea una instancia** en *Instancias* (o usa la *Default*).
2. Elige tu nombre en *Jugar* → *Sesión*, o conecta Microsoft en *Ajustes* con tu **Azure Client ID** (`portal.azure.com` → *Microsoft Entra ID* → *App registrations* → *New registration* → copia el *Application (client) ID*).
3. Elige versión + modo y pulsa **JUGAR**.

Tus mundos están en `%APPDATA%\.minecraft\launcher\instances\<nombre>\` (saves, mods, config separados por instancia).

---

## 🛠️ Ejecutar desde código (desarrolladores)

```bat
REM Usa SIEMPRE el Python del proyecto (el de la Microsoft Store redirige %APPDATA%)
run.bat
```

Manual:

```bat
.venv-app\Scripts\python.exe -m pip install -r requirements.txt
.venv-app\Scripts\python.exe main.py
```

Estructura:

```
main.py                 Punto de entrada (splash → ventana)
launcher.py             Instalación/lanzamiento de Minecraft + Java
auth.py / modrinth.py   Cuentas Microsoft / API de Modrinth
updater.py              Auto-actualización desde GitHub Releases
ui/                     Interfaz (ventana, páginas, diálogos, workers, temas)
assets/                 Fondos para las portadas de instancias
```

---

## ❓ Preguntas frecuentes

- **¿Dónde están mis mundos?** En `%APPDATA%\.minecraft\launcher\instances\<instancia>\saves`.
- **¿Necesito Java?** No, se descarga solo. Si ya tienes uno compatible, también lo detecta.
- **¿NeoForge en 1.20.1?** La librería solo lista NeoForge desde la 1.20.2; para 1.20.1 usa Forge.
- **¿Un modpack se mezcla con mis mods?** No: al instalarlo puedes crear una instancia nueva solo para él.
- **¿El antivirus avisa del .exe?** Es normal en ejecutables sin firmar: verifica que lo descargaste de los Releases oficiales.

---

© 2026 Ocelote9547 — Todos los derechos reservados.
