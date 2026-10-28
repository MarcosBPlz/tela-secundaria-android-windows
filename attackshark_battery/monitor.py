"""Escuta o canal de bateria do receptor e do mouse no cabo, somente leitura."""
import collections
import threading
import time

from .protocol import BATTERY_USAGE_PAGE, PRODUCTS, VENDOR_ID, parse

RESCAN_SECONDS = 3
CONFIRM_FRAMES = 2        # um valor so vale quando chega repetido (filtra o "01 64" de reconexao)
FLAP_WINDOW = 60          # s
FLAP_THRESHOLD = 4        # trocas bateria<->energia nesse intervalo = mau contato no cabo/dock


def is_battery_candidate(d):
    """Colecao que pode carregar o frame de bateria: a 0x0A conhecida ou uma vendor-defined
    (outros modelos podem usar outra). Teclado/mouse padrao ficam de fora (o Windows nem deixa ler)."""
    return (d["usage_page"] == BATTERY_USAGE_PAGE or d["usage_page"] >= 0xFF00) and d["input_len"] >= 5


class _Source:
    """Estado de filtragem de um dispositivo (receptor ou cabo)."""

    def __init__(self):
        self.pending = None        # (state, level) aguardando confirmacao
        self.count = 0
        self.last_raw_power = None


class BatteryMonitor:
    """Mantem a ultima leitura valida. on_frame(frame, pid) e chamado a cada frame aceito."""

    def __init__(self, on_frame=None):
        self.on_frame = on_frame
        self.lock = threading.Lock()
        self.frame = None
        self.source_pid = None
        self.last_seen = 0.0
        self.present = []          # pids com canal candidato presentes agora
        self.devices = []          # colecoes candidatas (para o diagnostico)
        self.recent = collections.deque(maxlen=12)   # (hora, pid, bytes crus) para o diagnostico
        self._sources = {}
        self._power_flips = []     # horarios das trocas bateria<->energia (frames crus)
        self._active = set()
        self._stop = threading.Event()

    def start(self):
        threading.Thread(target=self._scan_loop, daemon=True).start()

    def stop(self):
        self._stop.set()

    def flapping(self, now=None):
        """True se o contato de energia esta oscilando (ex.: cabo frouxo, mouse mal encaixado na dock)."""
        now = time.time() if now is None else now
        with self.lock:
            self._power_flips = [t for t in self._power_flips if now - t <= FLAP_WINDOW]
            return len(self._power_flips) >= FLAP_THRESHOLD

    def feed(self, f, pid, now=None):
        """Processa um frame ja decodificado. Retorna True se virou a leitura oficial.
        `now` permite reprocessar capturas com o horario original."""
        now = time.time() if now is None else now
        with self.lock:
            src = self._sources.setdefault(pid, _Source())
            if src.last_raw_power is not None and f.on_power != src.last_raw_power:
                self._power_flips.append(now)
            src.last_raw_power = f.on_power
            key = (f.state, f.level)
            if key == src.pending:
                src.count += 1
            else:
                src.pending, src.count = key, 1
            if src.count < CONFIRM_FRAMES:
                return False
            self.frame, self.source_pid, self.last_seen = f, pid, now
        if self.on_frame:
            self.on_frame(f, pid)
        return True

    def snapshot(self):
        with self.lock:
            return self.frame, self.source_pid, self.last_seen, list(self.present)

    def _scan_loop(self):
        from .hidread import enumerate_interfaces   # so existe no Windows; import tardio deixa testar a logica
        known = [(VENDOR_ID, pid) for pid in PRODUCTS]
        while not self._stop.is_set():
            try:
                devs = [d for d in enumerate_interfaces(known, vendors={VENDOR_ID}) if is_battery_candidate(d)]
            except OSError:
                devs = []
            with self.lock:
                self.present = sorted({d["product_id"] for d in devs})
                self.devices = devs
            for d in devs:
                if d["path"] not in self._active:
                    self._active.add(d["path"])
                    threading.Thread(target=self._read_loop, args=(d,), daemon=True).start()
            self._stop.wait(RESCAN_SECONDS)

    def _read_loop(self, d):
        from .hidread import ReadOnlyHid
        h = None
        try:
            h = ReadOnlyHid(d["path"], d["input_len"])
            while not self._stop.is_set():
                data = h.read()
                f = parse(data)
                if f is not None:
                    with self.lock:
                        self.recent.append((time.time(), d["product_id"], data[:8]))
                    self.feed(f, d["product_id"])
        except OSError:
            pass  # dispositivo removido (cabo desconectado, receptor tirado)
        finally:
            if h:
                h.close()
            self._active.discard(d["path"])

