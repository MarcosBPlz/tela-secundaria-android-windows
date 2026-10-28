"""Leitura da temperatura do computador no Windows, sem bloquear o servidor.

O Windows não expõe a temperatura da CPU de forma padrão para programas comuns.
Este módulo tenta, em ordem:
  1. LibreHardwareMonitor / OpenHardwareMonitor com o "Remote Web Server" ligado
     (http://127.0.0.1:8085/data.json) — CPU e GPU, funciona sem administrador.
  2. LibreHardwareMonitor / OpenHardwareMonitor via WMI (programa aberto).
  3. nvidia-smi — temperatura da placa de vídeo NVIDIA.
  4. Zona térmica ACPI do Windows (só funciona em alguns PCs, como administrador).
A leitura roda numa thread separada a cada poucos segundos e fica em cache.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request

INTERVAL = 5.0
_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _run(cmd: list[str], timeout: float = 4.0) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                             creationflags=_NO_WINDOW)
        return out.stdout or ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _num(text) -> float | None:
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(text or ""))
    return float(m.group(0).replace(",", ".")) if m else None


def _pick_cpu(sensors: list[tuple[str, str, float]]) -> tuple[float, str] | None:
    """sensors: (hardware/parent name, sensor name, value)."""
    cpu = [s for s in sensors if re.search(r"cpu|ryzen|intel|core", s[0], re.I) and not re.search(r"gpu|graphics|radeon|geforce|nvidia", s[0], re.I)]
    for pattern in (r"package", r"tctl|tdie", r"core.*(average|max)", r"core"):
        hits = [s for s in cpu if re.search(pattern, s[1], re.I) and 0 < s[2] < 125]
        if hits:
            return round(max(h[2] for h in hits)), "CPU"
    gpu = [s for s in sensors if re.search(r"gpu|nvidia|radeon|geforce", s[0] + " " + s[1], re.I) and 0 < s[2] < 125]
    if gpu:
        core = [g for g in gpu if re.search(r"core|gpu$", g[1], re.I)] or gpu
        return round(core[0][2]), "GPU"
    return None


def _from_web_server() -> tuple[float, str] | None:
    for port in (8085,):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/data.json", timeout=1.5) as resp:
                tree = json.loads(resp.read().decode("utf-8", "replace"))
        except (OSError, ValueError):
            continue
        sensors: list[tuple[str, str, float]] = []

        def walk(node, hardware=""):
            text = node.get("Text", "")
            children = node.get("Children", []) or []
            # Nós de hardware têm um ImageURL de chip/placa; usamos o nome do nível acima dos grupos
            is_group = text.lower() in {"temperatures", "temperaturas"}
            if is_group:
                for c in children:
                    v = _num(c.get("Value"))
                    if v is not None:
                        sensors.append((hardware, c.get("Text", ""), v))
                return
            for c in children:
                walk(c, text)

        walk(tree)
        found = _pick_cpu(sensors)
        if found:
            return found
    return None


def _from_wmi_hwmonitor() -> tuple[float, str] | None:
    if os.name != "nt":
        return None
    script = (
        "foreach($ns in 'root/LibreHardwareMonitor','root/OpenHardwareMonitor'){"
        "try{Get-CimInstance -Namespace $ns -ClassName Sensor -ErrorAction Stop|"
        "Where-Object SensorType -eq 'Temperature'|"
        "ForEach-Object{\"$($_.Parent)|$($_.Name)|$($_.Value)\"};break}catch{}}"
    )
    out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=6)
    sensors = []
    for line in out.splitlines():
        parts = line.strip().split("|")
        if len(parts) == 3 and _num(parts[2]) is not None:
            sensors.append((parts[0], parts[1], _num(parts[2])))
    return _pick_cpu(sensors)


def _from_nvidia() -> tuple[float, str] | None:
    exe = shutil.which("nvidia-smi") or r"C:\Windows\System32\nvidia-smi.exe"
    if not os.path.exists(exe):
        return None
    out = _run([exe, "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"])
    v = _num(out.splitlines()[0] if out.strip() else "")
    return (round(v), "GPU") if v is not None and 0 < v < 125 else None


def _from_acpi() -> tuple[float, str] | None:
    if os.name != "nt":
        return None
    script = ("try{(Get-CimInstance -Namespace root/wmi -ClassName MSAcpi_ThermalZoneTemperature "
              "-ErrorAction Stop|Select-Object -First 1).CurrentTemperature}catch{}")
    v = _num(_run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=6))
    if v:
        c = v / 10 - 273.15
        if 0 < c < 125:
            return round(c), "Sistema"
    return None


class TemperatureMonitor:
    def __init__(self):
        self.value: float | None = None
        self.source: str | None = None
        self._dead: set[str] = set()
        self._fails: dict[str, int] = {}
        threading.Thread(target=self._loop, daemon=True).start()

    def snapshot(self) -> dict:
        return {"temperature": self.value, "temperature_source": self.source}

    def _loop(self):
        readers = [("web", _from_web_server), ("nvidia", _from_nvidia),
                   ("wmi", _from_wmi_hwmonitor), ("acpi", _from_acpi)]
        while True:
            found = None
            for name, fn in readers:
                # Fontes lentas que nunca funcionaram são consultadas só de vez em quando
                if name in self._dead and int(time.time()) % 60 >= INTERVAL:
                    continue
                try:
                    found = fn()
                except Exception:
                    found = None
                if found:
                    self._fails[name] = 0
                    self._dead.discard(name)
                    break
                self._fails[name] = self._fails.get(name, 0) + 1
                if self._fails[name] >= 2 and name != "web":
                    self._dead.add(name)
            self.value, self.source = (found if found else (None, None))
            time.sleep(INTERVAL)
