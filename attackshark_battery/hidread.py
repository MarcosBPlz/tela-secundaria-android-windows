"""Acesso HID estritamente somente-leitura no Windows, sem dependencias externas.

Garantias (verificaveis no codigo abaixo):
  * Enumeracao via CfgMgr32 (lista de interfaces que o Windows ja conhece) e
    HidD_GetPreparsedData/HidP_GetCaps (descritor que o driver HID ja guardou
    em memoria). Nenhuma dessas chamadas gera trafego USB para o dispositivo.
  * Para ler caps, o dispositivo e aberto com acesso 0 (nem leitura nem escrita).
  * Para ler relatorios, e aberto com GENERIC_READ apenas. Sem GENERIC_WRITE o
    Windows recusa WriteFile/HidD_SetOutputReport/HidD_SetFeature (erro 5),
    entao e impossivel enviar dados ao mouse por este handle.
  * ReadFile so copia relatorios de entrada que o driver HID do Windows ja busca
    continuamente, com ou sem este programa aberto.
  * Nao usamos HidD_GetFeature/GetInputReport/Get*String: essas sim geram
    requisicoes ao dispositivo.
"""
import ctypes
import re
from ctypes import wintypes

GENERIC_READ = 0x80000000
FILE_SHARE_READ, FILE_SHARE_WRITE = 0x1, 0x2
OPEN_EXISTING = 3
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
CR_SUCCESS = 0
CM_GET_DEVICE_INTERFACE_LIST_PRESENT = 0
HIDP_STATUS_SUCCESS = 0x00110000


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


GUID_DEVINTERFACE_HID = GUID(0x4D1E55B2, 0xF16F, 0x11CF,
                             (ctypes.c_ubyte * 8)(0x88, 0xCB, 0x00, 0x11, 0x11, 0x00, 0x00, 0x30))


class HIDP_CAPS(ctypes.Structure):
    _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
                ("InputReportByteLength", wintypes.USHORT),
                ("OutputReportByteLength", wintypes.USHORT),
                ("FeatureReportByteLength", wintypes.USHORT),
                ("Reserved", wintypes.USHORT * 17)] + \
               [(n, wintypes.USHORT) for n in (
                   "NumberLinkCollectionNodes", "NumberInputButtonCaps", "NumberInputValueCaps",
                   "NumberInputDataIndices", "NumberOutputButtonCaps", "NumberOutputValueCaps",
                   "NumberOutputDataIndices", "NumberFeatureButtonCaps", "NumberFeatureValueCaps",
                   "NumberFeatureDataIndices")]


_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_k32.CreateFileW.restype = wintypes.HANDLE
_k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                          ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
_k32.ReadFile.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.CancelIoEx.argtypes = [wintypes.HANDLE, ctypes.c_void_p]

_cm = ctypes.WinDLL("cfgmgr32")
_cm.CM_Get_Device_Interface_List_SizeW.argtypes = [ctypes.POINTER(wintypes.ULONG), ctypes.POINTER(GUID),
                                                   wintypes.LPCWSTR, wintypes.ULONG]
_cm.CM_Get_Device_Interface_ListW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, ctypes.c_void_p,
                                              wintypes.ULONG, wintypes.ULONG]

_hid = ctypes.WinDLL("hid")
_hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
_hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
_hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]
_hid.HidP_GetCaps.restype = ctypes.c_long

_PATH_RE = re.compile(r"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})(?:&MI_([0-9A-F]{2}))?(?:&COL([0-9A-F]{2}))?", re.I)


def _open(path, access):
    h = _k32.CreateFileW(path, access, FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, 0, None)
    if h == INVALID_HANDLE_VALUE or h is None:
        raise OSError(ctypes.get_last_error(), f"CreateFileW falhou: {path}")
    return h


def _interface_paths():
    size = wintypes.ULONG(0)
    if _cm.CM_Get_Device_Interface_List_SizeW(ctypes.byref(size), ctypes.byref(GUID_DEVINTERFACE_HID),
                                              None, CM_GET_DEVICE_INTERFACE_LIST_PRESENT) != CR_SUCCESS:
        return []
    buf = ctypes.create_unicode_buffer(size.value)
    if _cm.CM_Get_Device_Interface_ListW(ctypes.byref(GUID_DEVINTERFACE_HID), None, buf, size.value,
                                         CM_GET_DEVICE_INTERFACE_LIST_PRESENT) != CR_SUCCESS:
        return []
    return [p for p in ctypes.wstring_at(ctypes.addressof(buf), size.value).split("\0") if p]


def _caps(path):
    h = _open(path, 0)  # acesso 0: so consulta ao driver, sem leitura nem escrita
    try:
        pp = ctypes.c_void_p()
        if not _hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            return None
        try:
            caps = HIDP_CAPS()
            if _hid.HidP_GetCaps(pp, ctypes.byref(caps)) != HIDP_STATUS_SUCCESS:
                return None
            return caps
        finally:
            _hid.HidD_FreePreparsedData(pp)
    finally:
        _k32.CloseHandle(h)


def enumerate_interfaces(ids=(), vendors=()):
    """Colecoes HID dos pares (vid, pid) em `ids` e de qualquer produto dos VIDs em `vendors`.
    Cada item: dict com path, vendor_id, product_id, interface_number, collection,
    usage_page, usage e tamanhos de relatorio."""
    wanted, vendors = set(ids), set(vendors)
    out = []
    for path in _interface_paths():
        m = _PATH_RE.search(path)
        if not m:
            continue
        vid, pid = int(m.group(1), 16), int(m.group(2), 16)
        if (vid, pid) not in wanted and vid not in vendors:
            continue
        try:
            caps = _caps(path)
        except OSError:
            continue
        if caps is None:
            continue
        out.append({
            "path": path, "vendor_id": vid, "product_id": pid,
            "interface_number": int(m.group(3), 16) if m.group(3) else -1,
            "collection": int(m.group(4), 16) if m.group(4) else 0,
            "usage_page": caps.UsagePage, "usage": caps.Usage,
            "input_len": caps.InputReportByteLength,
            "output_len": caps.OutputReportByteLength,
            "feature_len": caps.FeatureReportByteLength,
        })
    return out


class ReadOnlyHid:
    """Handle GENERIC_READ. read() bloqueia ate chegar um relatorio."""

    def __init__(self, path, report_len=64):
        self._h = _open(path, GENERIC_READ)
        self._len = max(report_len, 1)

    def read(self):
        buf = ctypes.create_string_buffer(self._len)
        n = wintypes.DWORD(0)
        if not _k32.ReadFile(self._h, buf, self._len, ctypes.byref(n), None):
            raise OSError(ctypes.get_last_error(), "ReadFile falhou")
        return buf.raw[:n.value]

    def close(self):
        if self._h:
            _k32.CancelIoEx(self._h, None)
            _k32.CloseHandle(self._h)
            self._h = None

