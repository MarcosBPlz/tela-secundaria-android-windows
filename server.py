from __future__ import annotations

import ctypes
import json
import mimetypes
import os
import re
import socket
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parent
MEDIA = ROOT / "media"
DATA = ROOT / "data"
MEDIA.mkdir(exist_ok=True)
DATA.mkdir(exist_ok=True)
SHOPPING_FILE = DATA / "shopping.json"
SETTINGS_FILE = DATA / "settings.json"
AGENDA_FILE = DATA / "agenda.json"
PORT = int(os.environ.get("TABLET_PANEL_PORT", "47811"))
last_cpu = None
from attackshark_battery.monitor import BatteryMonitor
from media_sessions import MediaSessionMonitor
from voice_assistant import VoiceAssistantError, process_voice_command
from temperature import TemperatureMonitor
battery_monitor = BatteryMonitor()
media_monitor = MediaSessionMonitor()
temperature_monitor = TemperatureMonitor()

default_layout = {
    "clock": {"x": 4, "y": 6, "w": 40, "h": 20},
    "weather": {"x": 80, "y": 6, "w": 16, "h": 18},
    "system": {"x": 4, "y": 34, "w": 46, "h": 15},
    "music": {"x": 4, "y": 53, "w": 46, "h": 17},
    "shopping": {"x": 53, "y": 36, "w": 43, "h": 52},
    "agenda": {"x": 53, "y": 6, "w": 25, "h": 27},
    "mouse": {"x": 68, "y": 93, "w": 28, "h": 5},
}


def get_settings():
    defaults = {"city": "São Paulo, SP", "darkness": 30, "accent": "#b58cff", "background": "", "wallpaper_fit": "cover", "wallpaper_zoom": 1.0, "ui_scale": 1.0, "widgets": {"clock": True, "weather": True, "system": True, "music": True, "shopping": True, "mouse": True, "agenda": True}, "layout": default_layout.copy()}
    if SETTINGS_FILE.exists():
        try:
            defaults.update(json.loads(SETTINGS_FILE.read_text("utf-8")))
        except (OSError, ValueError):
            pass
    return defaults

def save_settings(patch):
    allowed = {"city", "darkness", "accent", "background", "wallpaper_fit", "wallpaper_zoom", "ui_scale", "widgets", "layout", "design"}
    settings = get_settings()
    settings.update({k: v for k, v in patch.items() if k in allowed})
    settings["darkness"] = max(0, min(75, int(settings.get("darkness", 30))))
    settings["wallpaper_fit"] = "contain" if settings.get("wallpaper_fit") == "contain" else "cover"
    settings["wallpaper_zoom"] = max(1.0, min(2.5, float(settings.get("wallpaper_zoom", 1.0))))
    settings["ui_scale"] = max(0.65, min(1.35, float(settings.get("ui_scale", 1.0))))
    widget_defaults = {"clock": True, "weather": True, "system": True, "music": True, "shopping": True, "mouse": True, "agenda": True}
    incoming_widgets = settings.get("widgets", {})
    if not isinstance(incoming_widgets, dict):
        incoming_widgets = {}
    settings["widgets"] = {key: bool(incoming_widgets.get(key, value)) for key, value in widget_defaults.items()}
    incoming_layout = settings.get("layout", {})
    if not isinstance(incoming_layout, dict):
        incoming_layout = {}
    layout = {}
    for name, box in default_layout.items():
        source = incoming_layout.get(name, {})
        if not isinstance(source, dict):
            source = {}
        try:
            x = max(0.0, min(92.0, float(source.get("x", box["x"]))))
            y = max(0.0, min(94.0, float(source.get("y", box["y"]))))
            w = max(8.0, min(100.0 - x, float(source.get("w", box["w"]))))
            h = max(6.0, min(100.0 - y, float(source.get("h", box["h"]))))
        except (TypeError, ValueError):
            x, y, w, h = box["x"], box["y"], box["w"], box["h"]
        layout[name] = {"x": round(x, 2), "y": round(y, 2), "w": round(w, 2), "h": round(h, 2)}
    settings["layout"] = layout
    design = settings.get("design")
    try:
        settings["design"] = {"w": int(max(320, min(8000, float(design["w"])))), "h": int(max(240, min(8000, float(design["h"]))))}
    except (TypeError, ValueError, KeyError):
        settings.pop("design", None)
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), "utf-8")
    return settings


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def system_status() -> dict:
    global last_cpu
    result = {"cpu": None, "memory": None, "temperature": None}
    if os.name == "nt":
        class FILETIME(ctypes.Structure):
            _fields_ = [("low", ctypes.c_uint), ("high", ctypes.c_uint)]

        idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
        if ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            values = tuple((v.high << 32) | v.low for v in (idle, kernel, user))
            if last_cpu:
                delta = tuple(a - b for a, b in zip(values, last_cpu))
                total = delta[1] + delta[2]
                result["cpu"] = round(100 * (total - delta[0]) / total) if total else 0
            last_cpu = values

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(mem)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
            result["memory"] = {"percent": int(mem.dwMemoryLoad), "used_gb": round((mem.ullTotalPhys - mem.ullAvailPhys) / 2**30, 1),
                                 "total_gb": round(mem.ullTotalPhys / 2**30, 1)}
    result.update(temperature_monitor.snapshot())
    return result


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt, *args):
        print("[%s] %s" % (self.log_date_time_string(), fmt % args))

    def send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/voice/status":
            return self.send_json({"configured": True, "mode": "local"})
        if path == "/api/status":
            result = system_status()
            frame, pid, seen, present = battery_monitor.snapshot()
            age = max(0, time.time() - seen) if seen else None
            result["mouse_battery"] = {"percent": frame.level if frame and age is not None and age < 45 else None, "state": frame.state_code if frame and age is not None and age < 45 else None, "connected": bool(present), "age_seconds": round(age, 1) if age is not None else None}
            result["now_playing"] = media_monitor.snapshot()
            return self.send_json(result)
        if path == "/api/settings":
            return self.send_json(get_settings())
        if path == "/api/agenda":
            try:
                day = parse_qs(urlparse(self.path).query).get("date", [""])[0]
                items = json.loads(AGENDA_FILE.read_text("utf-8")) if AGENDA_FILE.exists() else []
                return self.send_json([item for item in items if item.get("date") == day])
            except (OSError, ValueError):
                return self.send_json([])
        if path == "/api/shopping":
            items = json.loads(SHOPPING_FILE.read_text("utf-8")) if SHOPPING_FILE.exists() else []
            return self.send_json(items)
        if path == "/api/backgrounds":
            items = [{"name": p.name, "url": "/media/" + p.name} for p in MEDIA.iterdir() if p.is_file()]
            return self.send_json(items)
        if path.startswith("/media/"):
            name = Path(unquote(path[len("/media/"):])).name
            file = MEDIA / name
            if file.is_file():
                self.path = "/media/" + name
                return super().do_GET()
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/voice/command":
            try:
                payload = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", "0")), 4096)))
                if not isinstance(payload, dict):
                    return self.send_json({"error": "Comando inválido."}, 400)
                origin = self.headers.get("Origin", "")
                if origin and urlparse(origin).netloc != self.headers.get("Host", ""):
                    return self.send_json({"error": "Origem não autorizada."}, 403)
                result = process_voice_command(payload.get("text", ""), payload.get("previous_response_id"))
                return self.send_json(result)
            except VoiceAssistantError as exc:
                return self.send_json({"error": str(exc)}, 503)
            except (ValueError, OSError, TypeError):
                return self.send_json({"error": "Não foi possível processar o comando de voz."}, 400)
        if parsed.path == "/api/settings":
            try:
                patch = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                patch = patch if isinstance(patch, dict) else {}
                user_agent = self.headers.get("User-Agent", "")
                if re.search(r"Android|iPhone|iPad|iPod", user_agent, re.IGNORECASE):
                    patch.pop("widgets", None)
                    patch.pop("layout", None)
                    patch.pop("design", None)
                return self.send_json(save_settings(patch))
            except (ValueError, OSError, TypeError):
                return self.send_json({"error": "Não foi possível salvar os ajustes."}, 400)
        if parsed.path == "/api/agenda":
            try:
                item = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                items = json.loads(AGENDA_FILE.read_text("utf-8")) if AGENDA_FILE.exists() else []
                if item.get("action") == "delete":
                    items = [entry for entry in items if entry.get("id") != item.get("id")]
                else:
                    text = str(item.get("text", "")).strip()[:120]
                    day = str(item.get("date", ""))
                    clock = str(item.get("time", ""))
                    if not text or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day) or not re.fullmatch(r"\d{2}:\d{2}", clock):
                        return self.send_json({"error": "Informe horário e compromisso."}, 400)
                    items.append({"id": str(time.time_ns()), "date": day, "time": clock, "text": text})
                AGENDA_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")
                day = str(item.get("date", ""))
                return self.send_json([entry for entry in items if entry.get("date") == day])
            except (ValueError, OSError, TypeError):
                return self.send_json({"error": "Não foi possível atualizar a agenda."}, 400)
        if parsed.path == "/api/shopping":
            try:
                item = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
                items = json.loads(SHOPPING_FILE.read_text("utf-8")) if SHOPPING_FILE.exists() else []
                if item.get("action") == "delete":
                    items = [x for x in items if x.get("id") != item.get("id")]
                elif item.get("action") == "toggle":
                    for x in items:
                        if x.get("id") == item.get("id"):
                            x["done"] = not x.get("done", False)
                elif item.get("text", "").strip():
                    items.append({"id": str(time.time_ns()), "text": item["text"].strip(), "done": False})
                SHOPPING_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), "utf-8")
                return self.send_json(items)
            except (ValueError, OSError):
                return self.send_json({"error": "Não foi possível atualizar a lista."}, 400)
        if parsed.path == "/api/background":
            name = parse_qs(parsed.query).get("name", [""])[0]
            name = Path(unquote(name)).name
            if not name or not re.fullmatch(r"[\w .()\-]+", name, re.UNICODE):
                return self.send_json({"error": "Nome de arquivo inválido."}, 400)
            if Path(name).suffix.lower() not in {".mp4", ".webm", ".mov", ".gif", ".png", ".jpg", ".jpeg", ".webp"}:
                return self.send_json({"error": "Formato não suportado."}, 400)
            length = int(self.headers.get("Content-Length", "0"))
            if length > 500 * 1024 * 1024:
                return self.send_json({"error": "O arquivo ultrapassa 500 MB."}, 413)
            (MEDIA / name).write_bytes(self.rfile.read(length))
            save_settings({"background": "/media/" + name})
            return self.send_json({"name": name, "url": "/media/" + name})
        return self.send_error(404)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/background/"):
            name = Path(unquote(parsed.path.rsplit("/", 1)[-1])).name
            file = MEDIA / name
            if file.is_file():
                file.unlink()
            if get_settings().get("background") == "/media/" + name:
                save_settings({"background": ""})
            return self.send_json({"ok": True})
        return self.send_error(404)


if __name__ == "__main__":
    battery_monitor.start()
    media_monitor.start()
    address = local_ip()
    print("Painel do tablet iniciado.")
    print(f"Neste PC: http://localhost:{PORT}")
    print(f"No tablet (mesmo Wi-Fi): http://{address}:{PORT}")
    print("Pressione Ctrl+C para encerrar.")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
