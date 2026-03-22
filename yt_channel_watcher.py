#!/usr/bin/env python3
"""
YouTube Channel Watcher v1.1.0
Prueft beim Systemstart alle abonnierten Kanaele auf neue Videos.
Keine API-Key notwendig - nutzt YouTube RSS-Feeds.

Autor:    Christian Diezinger  |  rabenstaub@gmail.com
Lizenz:   Freeware - private und gewerbliche Nutzung erlaubt
          Weitergabe nur unveraendert und kostenlos gestattet.
"""

import sys
import json
import os
import re
import traceback
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QScrollArea, QFrame,
    QSystemTrayIcon, QMenu, QCheckBox, QSizePolicy, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QUrl
from PyQt6.QtGui import (
    QIcon, QPixmap, QFont, QColor, QPainter, QAction, QDesktopServices
)

# ─── Konstanten ──────────────────────────────────────────────────────────────

APP_NAME     = "YouTube Channel Watcher"
APP_VERSION  = "1.2.0"
APP_DATE     = "2026-03-22"
APP_AUTHOR   = "Christian Diezinger"
APP_CONTACT  = "rabenstaub@gmail.com"
APP_KOFI     = "https://ko-fi.com/rabenstaub"
APP_GITHUB   = "https://github.com/Rabenstaub/yt-channel-watcher"
APP_API_URL  = "https://api.github.com/repos/Rabenstaub/yt-channel-watcher/releases/latest"
CONFIG_DIR  = Path(os.getenv("APPDATA", ".")) / "YTChannelWatcher"
CONFIG_FILE = CONFIG_DIR / "config.json"

DARK = {
    "bg":       "#12121e",
    "surface":  "#1a1a2e",
    "card":     "#16213e",
    "border":   "#2a2a4a",
    "accent":   "#e63946",
    "accent2":  "#ff6b6b",
    "text":     "#e0e0e0",
    "muted":    "#888899",
    "success":  "#2ed573",
    "warning":  "#ffa502",
}

STYLE = f"""
* {{ font-family: 'Segoe UI', Arial, sans-serif; }}
QMainWindow, QWidget {{
    background-color: {DARK['bg']};
    color: {DARK['text']};
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: {DARK['surface']};
    width: 8px;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {DARK['border']};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QPushButton {{
    background-color: {DARK['accent']};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: bold;
    font-size: 12px;
}}
QPushButton:hover {{ background-color: {DARK['accent2']}; }}
QPushButton:disabled {{ background-color: #333; color: #666; }}
QPushButton[secondary="true"] {{
    background-color: {DARK['border']};
    color: {DARK['muted']};
    font-weight: normal;
}}
QPushButton[secondary="true"]:hover {{
    background-color: #3a3a5a;
    color: {DARK['text']};
}}
QPushButton[danger="true"] {{
    background-color: #2a1020;
    color: {DARK['accent2']};
    font-weight: normal;
}}
QPushButton[danger="true"]:hover {{ background-color: #4a1830; }}
QPushButton[tab="true"] {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: {DARK['muted']};
    padding: 11px 22px;
    font-size: 13px;
    border-radius: 0;
}}
QPushButton[tab="true"][active="true"] {{
    color: {DARK['accent']};
    border-bottom: 2px solid {DARK['accent']};
    font-weight: bold;
}}
QLineEdit {{
    background-color: {DARK['surface']};
    border: 1px solid {DARK['border']};
    border-radius: 6px;
    padding: 7px 12px;
    color: {DARK['text']};
    font-size: 13px;
}}
QLineEdit:focus {{ border-color: {DARK['accent']}; }}
QFrame[card="true"] {{
    background-color: {DARK['card']};
    border-radius: 8px;
    border: 1px solid {DARK['border']};
}}
QCheckBox {{ color: {DARK['muted']}; font-size: 13px; spacing: 8px; }}
QCheckBox::indicator {{
    width: 16px; height: 16px;
    border: 2px solid {DARK['border']};
    border-radius: 3px;
    background: {DARK['surface']};
}}
QCheckBox::indicator:checked {{
    background-color: {DARK['accent']};
    border-color: {DARK['accent']};
}}
QToolTip {{
    background-color: {DARK['card']};
    color: {DARK['text']};
    border: 1px solid {DARK['border']};
    padding: 4px 8px;
    border-radius: 4px;
}}
"""

# ─── Config ──────────────────────────────────────────────────────────────────

def load_config() -> dict:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Sicherstellen dass alle Felder vorhanden sind
                if not isinstance(data.get("channels"), list):
                    data["channels"] = []
                return data
        except Exception:
            # Korrupte Config: Backup anlegen und neu starten
            backup = CONFIG_FILE.with_suffix(".bak")
            try:
                CONFIG_FILE.rename(backup)
            except Exception:
                pass
    return {"channels": [], "autostart": True}


def save_config(cfg: dict):
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        # Erst in Temp-Datei schreiben, dann umbenennen (atomarer Schreibvorgang)
        tmp = CONFIG_FILE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        tmp.replace(CONFIG_FILE)
    except Exception as e:
        print(f"[Config] Speichern fehlgeschlagen: {e}")


def set_autostart(enabled: bool):
    try:
        import winreg
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enabled:
            if getattr(sys, "frozen", False):
                exe = f'"{sys.executable}"'
            else:
                exe = f'"{sys.executable}" "{os.path.abspath(__file__)}"'
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe)
        else:
            try:
                winreg.DeleteValue(key, APP_NAME)
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        print(f"[Autostart] {e}")

# ─── YouTube Helpers ──────────────────────────────────────────────────────────

def http_get(url: str, timeout=20) -> bytes:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_rss(channel_id: str) -> tuple[str, list[dict]]:
    """Gibt (Kanalname, [video_dict, ...]) zurück."""
    data = http_get(f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}")
    ns = {
        "atom":  "http://www.w3.org/2005/Atom",
        "yt":    "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    root = ET.fromstring(data)
    name = root.findtext("atom:title", default=channel_id, namespaces=ns)
    videos = []
    for entry in root.findall("atom:entry", ns):
        vid_id    = entry.findtext("yt:videoId",     default="", namespaces=ns)
        title     = entry.findtext("atom:title",     default="", namespaces=ns)
        published = entry.findtext("atom:published", default="", namespaces=ns)
        link_el   = entry.find("atom:link", ns)
        link      = link_el.get("href", "") if link_el is not None else ""
        videos.append({"video_id": vid_id, "title": title,
                        "published": published, "link": link})
    return name, videos


def resolve_channel(text: str) -> tuple[str | None, str]:
    """Gibt (channel_id, info_text) zurück. channel_id=None bei Fehler."""
    text = text.strip()

    # Direkte UC-ID
    if re.match(r"^UC[a-zA-Z0-9_-]{22}$", text):
        return text, text

    # URL mit /channel/
    m = re.search(r"youtube\.com/channel/(UC[a-zA-Z0-9_-]{22})", text)
    if m:
        return m.group(1), m.group(1)

    # @Handle aus URL oder direkt
    m = re.search(r"youtube\.com/@([^/\s?&]+)", text)
    if m:
        handle = f"@{m.group(1)}"
    elif text.startswith("@"):
        handle = text
    else:
        handle = f"@{text}"

    # Kanalseite laden → channelId extrahieren
    try:
        html = http_get(f"https://www.youtube.com/{handle}").decode("utf-8", errors="replace")
        for pat in [
            r'"channelId":"(UC[a-zA-Z0-9_-]{22})"',
            r'"externalId":"(UC[a-zA-Z0-9_-]{22})"',
            r'channel/(UC[a-zA-Z0-9_-]{22})',
        ]:
            m2 = re.search(pat, html)
            if m2:
                return m2.group(1), handle
        return None, f"Kanal-ID nicht auf der Seite von {handle} gefunden"
    except Exception as e:
        return None, str(e)

# ─── Worker-Threads ───────────────────────────────────────────────────────────

class FetchThread(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(list)

    def __init__(self, config: dict):
        super().__init__()
        self.config = config

    def run(self):
        try:
            new_videos = []
            channels = self.config.get("channels", [])
            if not channels:
                self.finished.emit([])
                return
            for ch in channels:
                try:
                    self.progress.emit(f"Prüfe:  {ch.get('name', ch['id'])} …")
                    name, videos = fetch_rss(ch["id"])
                    ch["name"] = name
                    known = set(ch.get("last_video_ids", []))
                    fresh = [v for v in videos if v["video_id"] not in known]
                    ch["last_video_ids"] = [v["video_id"] for v in videos]
                    for v in fresh:
                        v["channel_name"] = name
                        v["channel_id"]   = ch["id"]
                        new_videos.append(v)
                except Exception as e:
                    self.progress.emit(f"Fehler bei {ch.get('name', ch['id'])}: {e}")
            self.finished.emit(new_videos)
        except Exception as e:
            print(f"[FetchThread] {e}\n{traceback.format_exc()}")
            self.finished.emit([])


class ResolveThread(QThread):
    done  = pyqtSignal(str, str, list)
    error = pyqtSignal(str)

    def __init__(self, text: str):
        super().__init__()
        self.text = text

    def run(self):
        try:
            ch_id, hint = resolve_channel(self.text)
            if not ch_id:
                self.error.emit(hint)
                return
            try:
                name, videos = fetch_rss(ch_id)
                ids = [v["video_id"] for v in videos]
                self.done.emit(ch_id, name, ids)
            except Exception as e:
                self.error.emit(f"RSS-Fehler: {e}")
        except Exception as e:
            print(f"[ResolveThread] {e}\n{traceback.format_exc()}")
            self.error.emit(str(e))


class ThumbnailThread(QThread):
    loaded = pyqtSignal(QPixmap)

    def __init__(self, video_id: str, parent=None):
        super().__init__(parent)
        self.video_id = video_id

    def run(self):
        try:
            data   = http_get(f"https://i.ytimg.com/vi/{self.video_id}/mqdefault.jpg", timeout=8)
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            if not pixmap.isNull():
                self.loaded.emit(pixmap)
        except Exception:
            pass

# ─── UI-Widgets ───────────────────────────────────────────────────────────────

def make_tray_icon() -> QIcon:
    px = QPixmap(32, 32)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(DARK["accent"]))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, 32, 32)
    p.setPen(QColor("white"))
    p.setFont(QFont("Arial", 14, QFont.Weight.Bold))
    p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, "▶")
    p.end()
    return QIcon(px)


class VideoCard(QFrame):
    def __init__(self, video: dict):
        super().__init__()
        self.video = video
        self._thumb_thread = None   # Referenz halten → kein GC-Absturz
        self.setProperty("card", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build()

    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 10, 12, 10)
        row.setSpacing(14)

        self.thumb = QLabel("▶")
        self.thumb.setFixedSize(124, 70)
        self.thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb.setFont(QFont("Segoe UI", 22))
        self.thumb.setStyleSheet(
            f"background:{DARK['border']}; border-radius:4px; color:{DARK['accent']};"
        )
        row.addWidget(self.thumb)

        vid_id = self.video.get("video_id", "")
        if vid_id:
            self._thumb_thread = ThumbnailThread(vid_id, self)
            self._thumb_thread.loaded.connect(self._set_thumb)
            self._thumb_thread.start()

        info = QVBoxLayout()
        info.setSpacing(3)

        ch = QLabel(self.video.get("channel_name", ""))
        ch.setStyleSheet(f"color:{DARK['accent']}; font-size:11px; font-weight:bold;")
        info.addWidget(ch)

        title = QLabel(self.video.get("title", ""))
        title.setWordWrap(True)
        title.setStyleSheet(f"color:{DARK['text']}; font-size:13px; font-weight:bold;")
        info.addWidget(title)

        pub = self.video.get("published", "")
        if pub:
            try:
                dt  = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                pub = dt.strftime("%d.%m.%Y  %H:%M")
            except Exception:
                pub = pub[:10]
            dl = QLabel(pub)
            dl.setStyleSheet(f"color:{DARK['muted']}; font-size:11px;")
            info.addWidget(dl)

        info.addStretch()
        row.addLayout(info, 1)

        btn = QPushButton("▶  Ansehen")
        btn.setFixedWidth(110)
        btn.clicked.connect(self._watch)
        row.addWidget(btn, 0, Qt.AlignmentFlag.AlignVCenter)

        seen_btn = QPushButton("✓")
        seen_btn.setFixedWidth(36)
        seen_btn.setToolTip("Als gesehen markieren – aus der Liste entfernen")
        seen_btn.setStyleSheet(
            "QPushButton { background-color: #1a3a1a; color: #2ed573; border-radius: 6px;"
            " padding: 7px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #2a5a2a; }"
        )
        seen_btn.clicked.connect(self._mark_seen)
        row.addWidget(seen_btn, 0, Qt.AlignmentFlag.AlignVCenter)

    def _set_thumb(self, px: QPixmap):
        try:
            scaled = px.scaled(124, 70,
                               Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
            self.thumb.setPixmap(scaled)
            self.thumb.setStyleSheet("border-radius:4px;")
            self.thumb.setText("")
        except Exception:
            pass

    def _mark_seen(self):
        self.setVisible(False)
        self.deleteLater()

    def _watch(self):
        url = self.video.get("link", "")
        if url:
            QDesktopServices.openUrl(QUrl(url))
            # Nur automatisch ausblenden wenn Einstellung aktiv
            cfg = load_config()
            if cfg.get("auto_hide_seen", True):
                QTimer.singleShot(2000, self._mark_seen)


class ChannelRow(QFrame):
    removed = pyqtSignal(str)

    def __init__(self, ch: dict):
        super().__init__()
        self.ch = ch
        self.setProperty("card", True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._build()

    def _build(self):
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 9, 14, 9)
        row.setSpacing(10)

        name = QLabel(f"<b>{self.ch.get('name', self.ch['id'])}</b>")
        name.setStyleSheet(f"color:{DARK['text']}; font-size:13px;")
        row.addWidget(name, 1)

        id_lbl = QLabel(self.ch["id"])
        id_lbl.setStyleSheet(f"color:{DARK['muted']}; font-size:11px;")
        row.addWidget(id_lbl)

        open_btn = QPushButton("Kanal öffnen")
        open_btn.setProperty("secondary", True)
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl(f"https://youtube.com/channel/{self.ch['id']}")
            )
        )
        row.addWidget(open_btn)

        del_btn = QPushButton("Entfernen")
        del_btn.setProperty("danger", True)
        del_btn.clicked.connect(lambda: self.removed.emit(self.ch["id"]))
        row.addWidget(del_btn)

# ─── Disclaimer-Dialog (Erst-Start) ──────────────────────────────────────────

class DisclaimerDialog(QWidget):
    accepted = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} - Nutzungsbedingungen")
        self.setFixedSize(560, 540)
        self.setStyleSheet(f"background:{DARK['bg']}; color:{DARK['text']};")
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(28, 24, 28, 20)
        vbox.setSpacing(14)

        # Titel
        title = QLabel(f"<b style='font-size:16px; color:{DARK['accent']};'>"
                       f"Willkommen beim {APP_NAME}</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(title)

        ver = QLabel(f"Version {APP_VERSION}  ·  {APP_AUTHOR}  ·  {APP_CONTACT}")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"color:{DARK['muted']}; font-size:11px;")
        vbox.addWidget(ver)

        # Scrollbarer Text
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border:1px solid {DARK['border']}; border-radius:6px; }}"
        )
        text_widget = QWidget()
        tl = QVBoxLayout(text_widget)
        tl.setContentsMargins(14, 14, 14, 14)

        disclaimer_html = f"""
<p style='color:{DARK['accent']}; font-weight:bold;'>Haftungsausschluss</p>
<p style='color:{DARK['muted']}; font-size:12px;'>
Die Nutzung dieser Software erfolgt auf eigene Gefahr. Der Anbieter übernimmt keine Gewähr
für die Richtigkeit, Vollständigkeit oder Aktualität der bereitgestellten Funktionen und Inhalte.
<br><br>
Es wird keine Haftung für Schäden übernommen, die direkt oder indirekt durch die Nutzung oder
Nichtnutzung der Software entstehen, sofern kein nachweislich vorsätzliches oder grob fahrlässiges
Verschulden vorliegt.
<br><br>
Der Anbieter behält sich vor, die Software jederzeit ohne Ankündigung zu ändern, zu erweitern
oder einzustellen.
</p>

<p style='color:{DARK['accent']}; font-weight:bold;'>Datenschutzerklärung</p>
<p style='color:{DARK['muted']}; font-size:12px;'>
Diese Software verarbeitet oder speichert keine personenbezogenen Daten.
Es werden keine Daten an Dritte übertragen, keine Nutzungsdaten analysiert und keine Verbindungen
zu externen Servern hergestellt, außer zum Abruf öffentlich zugänglicher YouTube-RSS-Feeds.
<br><br>
Alle Funktionen der Software laufen ausschließlich lokal auf dem Gerät des Nutzers.
</p>

<p style='color:{DARK['accent']}; font-weight:bold;'>Lizenz</p>
<p style='color:{DARK['muted']}; font-size:12px;'>
Freeware - private und gewerbliche Nutzung erlaubt.
Weitergabe nur unverändert und kostenlos gestattet.
Eine Nutzung des Namens, Logos oder Codes für eigene kommerzielle Produkte ist ohne
schriftliche Genehmigung nicht gestattet.
</p>

<p style='color:{DARK['accent']}; font-weight:bold;'>Impressum</p>
<p style='color:{DARK['muted']}; font-size:12px;'>
Christian Diezinger<br>
Hauptstraße 26<br>
87772 Pfaffenhausen<br>
Deutschland<br>
E-Mail: rabenstaub@gmail.com
</p>
"""
        lbl = QLabel(disclaimer_html)
        lbl.setWordWrap(True)
        lbl.setOpenExternalLinks(True)
        tl.addWidget(lbl)
        scroll.setWidget(text_widget)
        vbox.addWidget(scroll, 1)

        # Checkbox
        self.cb = QCheckBox(
            "Ich habe die Nutzungsbedingungen und den Haftungsausschluss\n"
            "gelesen und akzeptiere diese."
        )
        self.cb.setStyleSheet(f"color:{DARK['text']}; font-size:12px;")
        vbox.addWidget(self.cb)

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_decline = QPushButton("Ablehnen")
        self.btn_decline.setProperty("secondary", True)
        self.btn_decline.clicked.connect(QApplication.quit)

        self.btn_accept = QPushButton("Akzeptieren & Starten")
        self.btn_accept.setEnabled(False)
        self.btn_accept.clicked.connect(self._on_accept)

        self.cb.toggled.connect(self.btn_accept.setEnabled)

        btn_row.addWidget(self.btn_decline)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_accept)
        vbox.addLayout(btn_row)

    def _on_accept(self):
        self.accepted.emit()
        self.close()


# ─── Update-Check Thread ─────────────────────────────────────────────────────

class UpdateCheckThread(QThread):
    update_available = pyqtSignal(str, str)  # neue Version, Download-URL

    def run(self):
        try:
            data = http_get(APP_API_URL, timeout=10)
            import json as _json
            release = _json.loads(data)
            latest  = release.get("tag_name", "").lstrip("v")
            dl_url  = release.get("html_url", APP_GITHUB)

            # Versions-Vergleich
            def ver_tuple(v):
                try:
                    return tuple(int(x) for x in v.split("."))
                except Exception:
                    return (0,)

            if ver_tuple(latest) > ver_tuple(APP_VERSION):
                self.update_available.emit(latest, dl_url)
        except Exception:
            pass  # Kein Internet oder API-Fehler → still ignorieren


# ─── Haupt-Fenster ────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self, config: dict):
        super().__init__()
        self.config         = config
        self.fetch_thread   = None
        self.resolve_thread = None
        self._resolve_threads = []   # alle laufenden Threads festhalten
        self.setWindowTitle(f"{APP_NAME}  v{APP_VERSION}")
        self.setMinimumSize(720, 560)
        self.resize(800, 620)
        self._build_ui()
        self._build_tray()

        # Flag-Datei überwachen → Fenster zeigen wenn zweite Instanz gestartet wird
        self._flag_timer = QTimer(self)
        self._flag_timer.timeout.connect(self._check_show_flag)
        self._flag_timer.start(500)

        # Auto-Prüf-Timer
        self._auto_check_timer = QTimer(self)
        self._auto_check_timer.timeout.connect(self.start_fetch)
        self._start_auto_check_timer()

        # Update-Check beim Start (verzögert um 5 Sekunden)
        self._update_thread = None
        QTimer.singleShot(5000, self._check_for_update)

    # ── UI aufbauen ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        vbox = QVBoxLayout(root)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        vbox.addWidget(self._make_header())
        vbox.addWidget(self._make_tabbar())

        # Update-Banner (anfangs versteckt)
        self.update_banner = QWidget()
        self.update_banner.setStyleSheet(
            "background:#1a3a1a; border-bottom:1px solid #2ed573;"
        )
        banner_row = QHBoxLayout(self.update_banner)
        banner_row.setContentsMargins(16, 6, 16, 6)
        self.update_banner_lbl = QLabel("")
        self.update_banner_lbl.setStyleSheet("color:#2ed573; font-size:12px;")
        banner_row.addWidget(self.update_banner_lbl)
        banner_row.addStretch()
        self.update_banner_btn = QPushButton("⬇  Jetzt herunterladen")
        self.update_banner_btn.setStyleSheet(
            "QPushButton { background:#2ed573; color:#0a1a0a; border-radius:5px;"
            " padding:4px 12px; font-weight:bold; font-size:12px; }"
            "QPushButton:hover { background:#4ef593; }"
        )
        banner_row.addWidget(self.update_banner_btn)
        dismiss_btn = QPushButton("✕")
        dismiss_btn.setFixedWidth(28)
        dismiss_btn.setStyleSheet(
            "QPushButton { background:transparent; color:#2ed573; border:none; font-size:14px; }"
            "QPushButton:hover { color:white; }"
        )
        dismiss_btn.clicked.connect(self.update_banner.hide)
        banner_row.addWidget(dismiss_btn)
        self.update_banner.hide()
        vbox.addWidget(self.update_banner)

        self.page_videos   = self._make_page_videos()
        self.page_channels = self._make_page_channels()
        self.page_settings = self._make_page_settings()
        self.page_help     = self._make_page_help()

        for p in [self.page_videos, self.page_channels, self.page_settings, self.page_help]:
            vbox.addWidget(p)

        self.page_channels.hide()
        self.page_settings.hide()
        self.page_help.hide()

    def _make_header(self):
        hdr = QWidget()
        hdr.setFixedHeight(58)
        hdr.setStyleSheet(
            f"background:{DARK['surface']}; border-bottom:1px solid {DARK['border']};"
        )
        row = QHBoxLayout(hdr)
        row.setContentsMargins(20, 0, 20, 0)

        ico = QLabel("📺")
        ico.setFont(QFont("Segoe UI", 18))
        row.addWidget(ico)

        ttl = QLabel(f"<b>{APP_NAME}</b>")
        ttl.setStyleSheet(f"color:{DARK['accent']}; font-size:16px; margin-left:6px;")
        row.addWidget(ttl)
        row.addStretch()

        self.status_lbl = QLabel("Bereit")
        self.status_lbl.setStyleSheet(f"color:{DARK['muted']}; font-size:12px;")
        row.addWidget(self.status_lbl)

        self.refresh_btn = QPushButton("🔄  Jetzt prüfen")
        self.refresh_btn.setFixedHeight(34)
        self.refresh_btn.clicked.connect(self.start_fetch)
        row.addWidget(self.refresh_btn)
        return hdr

    def _make_tabbar(self):
        bar = QWidget()
        bar.setFixedHeight(42)
        bar.setStyleSheet(
            f"background:{DARK['bg']}; border-bottom:1px solid {DARK['border']};"
        )
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 0, 0, 0)
        row.setSpacing(0)

        self.tabs = []
        for i, lbl in enumerate(["Neue Videos", "Kanäle verwalten", "Einstellungen", "Hilfe"]):
            btn = QPushButton(lbl)
            btn.setProperty("tab", True)
            btn.setProperty("active", i == 0)
            btn.clicked.connect(lambda _, idx=i: self._switch_tab(idx))
            row.addWidget(btn)
            self.tabs.append(btn)

        row.addStretch()
        return bar

    def _switch_tab(self, idx: int):
        for i, btn in enumerate(self.tabs):
            btn.setProperty("active", i == idx)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        for i, p in enumerate([self.page_videos, self.page_channels, self.page_settings, self.page_help]):
            p.setVisible(i == idx)

    # ── Seite: Neue Videos ───────────────────────────────────────────────────

    def _make_page_videos(self):
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(20, 16, 20, 16)
        vbox.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        self.videos_inner  = QWidget()
        self.videos_layout = QVBoxLayout(self.videos_inner)
        self.videos_layout.setSpacing(8)
        self.videos_layout.setContentsMargins(0, 0, 6, 0)

        self.empty_lbl = QLabel(
            "Noch keine neuen Videos - klicke auf  🔄  Jetzt prüfen\n"
            "oder warte auf den nächsten Windows-Start."
        )
        self.empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_lbl.setStyleSheet(
            f"color:{DARK['muted']}; font-size:13px; padding:50px 20px;"
        )
        self.empty_lbl.setWordWrap(True)
        self.videos_layout.addWidget(self.empty_lbl)
        self.videos_layout.addStretch()

        scroll.setWidget(self.videos_inner)
        vbox.addWidget(scroll)
        return page

    # ── Seite: Kanäle ────────────────────────────────────────────────────────

    def _make_page_channels(self):
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(20, 16, 20, 16)
        vbox.setSpacing(10)

        add_frame = QFrame()
        add_frame.setProperty("card", True)
        add_row = QHBoxLayout(add_frame)
        add_row.setContentsMargins(12, 10, 12, 10)

        self.ch_input = QLineEdit()
        self.ch_input.setPlaceholderText(
            "YouTube-URL, @Handle oder Kanal-ID  (z. B. @MythenMetzger)"
        )
        self.ch_input.returnPressed.connect(self.add_channel)
        add_row.addWidget(self.ch_input)

        self.add_btn = QPushButton("+  Hinzufügen")
        self.add_btn.setFixedWidth(140)
        self.add_btn.clicked.connect(self.add_channel)
        add_row.addWidget(self.add_btn)
        vbox.addWidget(add_frame)

        self.add_status = QLabel("")
        self.add_status.setStyleSheet(
            f"color:{DARK['muted']}; font-size:11px; padding-left:4px;"
        )
        vbox.addWidget(self.add_status)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.chs_inner  = QWidget()
        self.chs_layout = QVBoxLayout(self.chs_inner)
        self.chs_layout.setSpacing(6)
        self.chs_layout.setContentsMargins(0, 0, 6, 0)
        self.chs_layout.addStretch()
        scroll.setWidget(self.chs_inner)
        vbox.addWidget(scroll, 1)

        self._refresh_channel_list()
        return page

    # ── Seite: Einstellungen ─────────────────────────────────────────────────

    def _make_page_settings(self):
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(20, 16, 20, 16)
        vbox.setSpacing(12)

        card = QFrame()
        card.setProperty("card", True)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 14, 18, 14)
        cl.setSpacing(10)

        cl.addWidget(QLabel("<b style='font-size:14px;'>Einstellungen</b>"))

        self.autostart_cb = QCheckBox("Automatisch mit Windows starten")
        self.autostart_cb.setChecked(self.config.get("autostart", True))
        self.autostart_cb.toggled.connect(self._toggle_autostart)
        cl.addWidget(self.autostart_cb)

        self.autohide_cb = QCheckBox("Gesehene Videos automatisch aus der Liste entfernen")
        self.autohide_cb.setChecked(self.config.get("auto_hide_seen", True))
        self.autohide_cb.toggled.connect(self._toggle_autohide)
        cl.addWidget(self.autohide_cb)

        hint = QLabel(
            "Beim Start prüft die App automatisch alle gespeicherten Kanäle\n"
            "und zeigt neue Videos an. Das Fenster erscheint nur wenn etwas Neues da ist.\n"
            "Videos können jederzeit manuell mit dem ✓-Button ausgeblendet werden."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{DARK['muted']}; font-size:11px;")
        cl.addWidget(hint)

        # Trennlinie
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color:{DARK['border']};")
        cl.addWidget(line)

        # Auto-Prüf-Intervall
        interval_lbl = QLabel("<b>Automatisch prüfen alle:</b>")
        interval_lbl.setStyleSheet(f"color:{DARK['text']}; font-size:13px;")
        cl.addWidget(interval_lbl)

        interval_row = QHBoxLayout()
        interval_row.setSpacing(8)
        intervals = [("Aus", 0), ("1 Std.", 1), ("2 Std.", 2), ("4 Std.", 4), ("6 Std.", 6)]
        current_interval = self.config.get("check_interval_hours", 4)
        self._interval_btns = []
        for label, hours in intervals:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(hours == current_interval)
            btn.setStyleSheet(
                f"QPushButton {{ background:{DARK['border']}; color:{DARK['muted']};"
                f" border-radius:6px; padding:6px 12px; font-size:12px; }}"
                f"QPushButton:checked {{ background:{DARK['accent']}; color:white; font-weight:bold; }}"
                f"QPushButton:hover {{ background:#3a3a5a; color:{DARK['text']}; }}"
            )
            btn.clicked.connect(lambda _, h=hours: self._set_interval(h))
            interval_row.addWidget(btn)
            self._interval_btns.append((btn, hours))
        interval_row.addStretch()
        cl.addLayout(interval_row)

        interval_hint = QLabel("Die App prüft automatisch im Hintergrund ob neue Videos verfügbar sind.")
        interval_hint.setWordWrap(True)
        interval_hint.setStyleSheet(f"color:{DARK['muted']}; font-size:11px;")
        cl.addWidget(interval_hint)

        vbox.addWidget(card)

        # ── Spenden-Card ─────────────────────────────────────────────────────
        donate_card = QFrame()
        donate_card.setProperty("card", True)
        donate_card.setStyleSheet(
            f"QFrame[card='true'] {{ background: #1a1a2e; border: 1px solid #3a3a6a; border-radius: 8px; }}"
        )
        dl = QVBoxLayout(donate_card)
        dl.setContentsMargins(18, 14, 18, 14)
        dl.setSpacing(8)

        kofi_row = QHBoxLayout()
        kofi_icon = QLabel("☕")
        kofi_icon.setFont(QFont("Segoe UI", 20))
        kofi_row.addWidget(kofi_icon)

        kofi_text = QVBoxLayout()
        kofi_title = QLabel("<b>App gefällt dir?</b>")
        kofi_title.setStyleSheet(f"color:{DARK['text']}; font-size:13px;")
        kofi_sub = QLabel("Die App ist und bleibt kostenlos. Über einen Kaffee freue ich mich sehr!")
        kofi_sub.setWordWrap(True)
        kofi_sub.setStyleSheet(f"color:{DARK['muted']}; font-size:11px;")
        kofi_text.addWidget(kofi_title)
        kofi_text.addWidget(kofi_sub)
        kofi_row.addLayout(kofi_text, 1)
        dl.addLayout(kofi_row)

        kofi_btn = QPushButton("☕  Ko-fi - Kaffee spendieren")
        kofi_btn.setStyleSheet(
            "QPushButton { background-color: #29abe0; color: white; border-radius: 6px;"
            " padding: 8px 16px; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background-color: #4dc3f0; }"
        )
        kofi_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl("https://ko-fi.com/rabenstaub"))
        )
        dl.addWidget(kofi_btn)

        vbox.addWidget(donate_card)
        vbox.addStretch()
        return page

    # ── Seite: Hilfe ─────────────────────────────────────────────────────────

    def _make_page_help(self):
        page = QWidget()
        vbox = QVBoxLayout(page)
        vbox.setContentsMargins(20, 16, 20, 16)
        vbox.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setSpacing(10)
        il.setContentsMargins(0, 0, 6, 0)

        def section(title, items):
            card = QFrame()
            card.setProperty("card", True)
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 12)
            cl.setSpacing(6)
            t = QLabel(f"<b style='font-size:13px; color:{DARK['accent']};'>{title}</b>")
            cl.addWidget(t)
            for icon, heading, body in items:
                row = QHBoxLayout()
                row.setSpacing(10)
                ico_lbl = QLabel(icon)
                ico_lbl.setFont(QFont("Segoe UI", 16))
                ico_lbl.setFixedWidth(28)
                row.addWidget(ico_lbl)
                txt = QVBoxLayout()
                h = QLabel(f"<b>{heading}</b>")
                h.setStyleSheet(f"color:{DARK['text']}; font-size:12px;")
                b = QLabel(body)
                b.setWordWrap(True)
                b.setStyleSheet(f"color:{DARK['muted']}; font-size:11px;")
                txt.addWidget(h)
                txt.addWidget(b)
                row.addLayout(txt, 1)
                cl.addLayout(row)
            return card

        il.addWidget(section("Erste Schritte", [
            ("📺", "Kanal hinzufügen",
             "Wechsle zum Tab 'Kanaele verwalten' und gib einen YouTube-Handle ein, "
             "z. B. @MythenMetzger, oder eine vollstaendige YouTube-URL. "
             "Klicke auf + Hinzufügen - die App loest den Kanal automatisch auf."),
            ("🔄", "Kanaele prüfen",
             "Klicke auf 'Jetzt prüfen' oben rechts. "
             "Die App prüft alle gespeicherten Kanaele auf neue Videos und zeigt sie sofort an."),
            ("🖱️", "Video ansehen",
             "Klicke auf den Button 'Ansehen' auf einer Videokarte - "
             "dein Browser öffnet das Video direkt auf YouTube."),
        ]))

        il.addWidget(section("Automatischer Start", [
            ("🚀", "Autostart mit Windows",
             "Die App trägt sich beim ersten Start automatisch in den Windows-Autostart ein. "
             "Beim nächsten PC-Start prüft sie still im Hintergrund alle Kanäle. "
             "Das Fenster erscheint nur wenn wirklich neue Videos gefunden wurden."),
            ("🔔", "System-Tray",
             "Die App läuft als Symbol in der Taskleiste (unten rechts, Pfeil ˄). "
             "Einfacher Klick öffnet das Fenster, Rechtsklick zeigt das Menü."),
            ("⚙️", "Autostart deaktivieren",
             "Im Tab 'Einstellungen' kann der automatische Windows-Start "
             "jederzeit ein- oder ausgeschaltet werden."),
        ]))

        il.addWidget(section("Kanäle verwalten", [
            ("➕", "Kanal hinzufügen",
             "Unterstützte Eingaben: @Handle (z. B. @MythenMetzger), "
             "vollständige YouTube-URL, oder direkte Kanal-ID (beginnt mit UC...)."),
            ("🗑️", "Kanal entfernen",
             "Klicke auf Entfernen neben dem gewuenschten Kanal. "
             "Bereits gespeicherte Videos dieses Kanals verschwinden beim nächsten Prüflauf."),
            ("🔗", "Kanal öffnen",
             "Mit Kanal oeffnen gelangst du direkt zur YouTube-Seite des Kanals."),
        ]))

        il.addWidget(section("Hinweise & Tipps", [
            ("🌐", "Keine Anmeldung nötig",
             "Die App nutzt die öffentlichen RSS-Feeds von YouTube. "
             "Es ist kein Google- oder YouTube-Konto erforderlich."),
            ("📋", "Nur öffentliche Kanäle",
             "Es können nur Kanäle hinzugefügt werden, "
             "deren Videos öffentlich zugänglich sind."),
            ("💾", "Lokale Datenspeicherung",
             "Alle Einstellungen und Kanaldaten werden lokal gespeichert unter: "
             "C:\\Users\\[Benutzername]\\AppData\\Roaming\\YTChannelWatcher\\"),
        ]))

        # Info-Leiste am Ende
        info_card = QFrame()
        info_card.setProperty("card", True)
        info_layout = QVBoxLayout(info_card)
        info_layout.setContentsMargins(16, 10, 16, 10)
        info_lbl = QLabel(
            f"<b>{APP_NAME}</b>  v{APP_VERSION}  ·  {APP_DATE}<br>"
            f"Entwickelt von {APP_AUTHOR}  ·  "
            f"<a href='mailto:{APP_CONTACT}' style='color:{DARK['accent']};'>{APP_CONTACT}</a>"
        )
        info_lbl.setOpenExternalLinks(True)
        info_lbl.setStyleSheet(f"color:{DARK['muted']}; font-size:11px;")
        info_layout.addWidget(info_lbl)
        il.addWidget(info_card)
        il.addStretch()

        scroll.setWidget(inner)
        vbox.addWidget(scroll)
        return page

    # ── Tray ─────────────────────────────────────────────────────────────────

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_tray_icon(), self)
        self.tray.setToolTip(APP_NAME)

        menu = QMenu()
        menu.setStyleSheet(
            f"QMenu {{ background:{DARK['card']}; color:{DARK['text']};"
            f" border:1px solid {DARK['border']}; }}"
            f"QMenu::item:selected {{ background:{DARK['border']}; }}"
        )
        a_open  = QAction("📺  Öffnen", self)
        a_check = QAction("🔄  Jetzt prüfen", self)
        a_quit  = QAction("✕  Beenden", self)
        a_open.triggered.connect(self._show_window)
        a_check.triggered.connect(self.start_fetch)
        a_quit.triggered.connect(QApplication.quit)
        menu.addAction(a_open)
        menu.addAction(a_check)
        menu.addSeparator()
        menu.addAction(a_quit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._show_window()

    def _show_window(self):
        self.show()
        self.setWindowState(
            (self.windowState() & ~Qt.WindowState.WindowMinimized)
            | Qt.WindowState.WindowActive
        )
        self.raise_()
        self.activateWindow()
        # Windows-API: Fenster wirklich in den Vordergrund zwingen
        try:
            import ctypes
            hwnd = int(self.winId())
            ctypes.windll.user32.ShowWindow(hwnd, 9)       # SW_RESTORE
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            ctypes.windll.user32.SetActiveWindow(hwnd)
        except Exception:
            pass

    # ── Logik ─────────────────────────────────────────────────────────────────

    def _set_interval(self, hours: int):
        self.config["check_interval_hours"] = hours
        save_config(self.config)
        # Buttons aktualisieren
        for btn, h in self._interval_btns:
            btn.setChecked(h == hours)
        self._start_auto_check_timer()

    def _start_auto_check_timer(self):
        self._auto_check_timer.stop()
        hours = self.config.get("check_interval_hours", 4)
        if hours > 0:
            self._auto_check_timer.start(hours * 60 * 60 * 1000)

    def _toggle_autohide(self, on: bool):
        self.config["auto_hide_seen"] = on
        save_config(self.config)

    def _toggle_autostart(self, on: bool):
        self.config["autostart"] = on
        save_config(self.config)
        set_autostart(on)

    def _refresh_channel_list(self):
        while self.chs_layout.count() > 1:
            item = self.chs_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        for ch in self.config.get("channels", []):
            row = ChannelRow(ch)
            row.removed.connect(self._remove_channel)
            self.chs_layout.insertWidget(self.chs_layout.count() - 1, row)

    def add_channel(self):
        text = self.ch_input.text().strip()
        if not text:
            return
        self.add_btn.setEnabled(False)
        self._set_add_status("Kanal wird aufgelöst …", DARK["muted"])

        t = ResolveThread(text)
        t.done.connect(self._on_channel_resolved)
        t.error.connect(self._on_channel_error)
        t.finished.connect(lambda: self._resolve_threads.remove(t) if t in self._resolve_threads else None)
        self._resolve_threads.append(t)
        t.start()

    def _on_channel_resolved(self, ch_id: str, name: str, init_ids: list):
        existing = [ch["id"] for ch in self.config.get("channels", [])]
        if ch_id in existing:
            self._set_add_status("Kanal ist bereits in der Liste.", DARK["warning"])
            self.add_btn.setEnabled(True)
            return
        ch = {"id": ch_id, "name": name, "last_video_ids": init_ids}
        self.config.setdefault("channels", []).append(ch)
        save_config(self.config)
        self.ch_input.clear()
        self._set_add_status(f"✓  »{name}« wurde hinzugefügt!", DARK["success"])
        self._refresh_channel_list()
        self.add_btn.setEnabled(True)

    def _on_channel_error(self, msg: str):
        self._set_add_status(f"Fehler: {msg}", DARK["accent2"])
        self.add_btn.setEnabled(True)

    def _set_add_status(self, text: str, color: str):
        self.add_status.setText(text)
        self.add_status.setStyleSheet(f"color:{color}; font-size:11px; padding-left:4px;")

    def _remove_channel(self, ch_id: str):
        self.config["channels"] = [
            ch for ch in self.config.get("channels", []) if ch["id"] != ch_id
        ]
        save_config(self.config)
        self._refresh_channel_list()

    def start_fetch(self):
        if self.fetch_thread and self.fetch_thread.isRunning():
            return
        if not self.config.get("channels"):
            self.status_lbl.setText("Keine Kanäle konfiguriert.")
            self._switch_tab(1)
            self._show_window()
            return
        self.refresh_btn.setEnabled(False)
        self.status_lbl.setText("Prüfe Kanäle …")

        self.fetch_thread = FetchThread(self.config)
        self.fetch_thread.progress.connect(self.status_lbl.setText)
        self.fetch_thread.finished.connect(self._on_fetch_done)
        self.fetch_thread.start()

    def _on_fetch_done(self, new_videos: list):
        try:
            save_config(self.config)
            self.refresh_btn.setEnabled(True)

            count = len(new_videos)
            self.status_lbl.setText(
                f"Fertig - {count} neue(s) Video(s)" if count else "Fertig - Alles aktuell"
            )

            # Video-Liste leeren
            while self.videos_layout.count() > 1:
                item = self.videos_layout.takeAt(0)
                if item and item.widget():
                    item.widget().deleteLater()

            if new_videos:
                self.empty_lbl.hide()
                for v in new_videos:
                    self.videos_layout.insertWidget(
                        self.videos_layout.count() - 1, VideoCard(v)
                    )
                self._switch_tab(0)
                self._show_window()
                self.tray.showMessage(
                    APP_NAME,
                    f"🎬  {count} neue(s) Video(s) gefunden!",
                    QSystemTrayIcon.MessageIcon.Information,
                    6000,
                )
            else:
                self.empty_lbl.show()
        except Exception as e:
            print(f"[_on_fetch_done] {e}\n{traceback.format_exc()}")

    def _check_for_update(self):
        self._update_thread = UpdateCheckThread()
        self._update_thread.update_available.connect(self._show_update_banner)
        self._update_thread.start()

    def _show_update_banner(self, new_version: str, dl_url: str):
        self.update_banner_lbl.setText(
            f"🎉  Neue Version verfügbar: v{new_version}  "
            f"(installiert: v{APP_VERSION})"
        )
        self.update_banner_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(dl_url))
        )
        self.update_banner.show()
        # Tray-Benachrichtigung
        self.tray.showMessage(
            f"{APP_NAME} – Update verfügbar",
            f"Version {new_version} ist verfügbar. Klicke auf das Fenster um zu aktualisieren.",
            QSystemTrayIcon.MessageIcon.Information,
            8000,
        )

    def _check_show_flag(self):
        try:
            if SHOW_FLAG.exists():
                SHOW_FLAG.unlink()
                self._show_window()
        except Exception:
            pass

    # ── Schließen → Tray ─────────────────────────────────────────────────────

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            APP_NAME,
            "Läuft im Hintergrund. Rechtsklick auf das Tray-Symbol zum Beenden.",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

# ─── main ─────────────────────────────────────────────────────────────────────

SHOW_FLAG = CONFIG_DIR / "show_window.flag"


def _single_instance_check() -> bool:
    """
    Prueft ob bereits eine Instanz laeuft (via Mutex).
    Falls ja: Flag-Datei schreiben damit die laufende Instanz sich zeigt.
    Gibt False zurueck wenn diese Instanz sich beenden soll.
    """
    try:
        import ctypes
        MUTEX_NAME = "YTChannelWatcher_SingleInstance_Mutex"
        ctypes.windll.kernel32.CreateMutexW(None, True, MUTEX_NAME)
        last_error = ctypes.windll.kernel32.GetLastError()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            # Laufende Instanz signalisieren: Fenster zeigen
            try:
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                SHOW_FLAG.touch()
            except Exception:
                pass
            return False
        return True
    except Exception:
        return True


def main():
    def excepthook(exc_type, exc_value, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        log_path = CONFIG_DIR / "crash.log"
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n{datetime.now()}\n{msg}\n")
        except Exception:
            pass
        try:
            app = QApplication.instance()
            if app:
                QMessageBox.critical(None, f"{APP_NAME} - Fehler",
                                     f"Ein unerwarteter Fehler ist aufgetreten:\n\n{exc_value}\n\n"
                                     f"Details in:\n{log_path}")
        except Exception:
            pass

    sys.excepthook = excepthook

    # Einzelinstanz-Prüfung: läuft schon eine Instanz → Fenster zeigen & beenden
    if not _single_instance_check():
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(STYLE)

    config = load_config()

    def start_app():
        set_autostart(config.get("autostart", True))
        win = MainWindow(config)
        first_run = not bool(config.get("channels"))
        # Fenster zeigen wenn: erster Start, keine Kanäle, oder --show Argument
        if first_run or "--show" in sys.argv:
            win.show()
            win._switch_tab(1 if first_run else 0)
        else:
            QTimer.singleShot(800, win.start_fetch)
        app._main_window = win

    # Disclaimer beim allerersten Start anzeigen
    disclaimer_accepted = config.get("disclaimer_accepted", False)
    if not disclaimer_accepted:
        dlg = DisclaimerDialog()
        dlg.show()
        def on_accept():
            config["disclaimer_accepted"] = True
            save_config(config)
            start_app()
        dlg.accepted.connect(on_accept)
        app._disclaimer = dlg
    else:
        start_app()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
