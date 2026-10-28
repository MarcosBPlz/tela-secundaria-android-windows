"""Tela Tablet na bandeja do Windows (área de ícones ocultos).

Roda o servidor do painel sem janela de terminal e mostra um ícone perto do relógio.
Clique no ícone: abre o painel. Botão direito: menu com endereço do tablet, iniciar com o
Windows e sair. Usa só a biblioteca padrão do Python (ctypes), nada para instalar.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))
(ROOT / "data").mkdir(exist_ok=True)
LOG = open(ROOT / "data" / "tray.log", "a", encoding="utf-8", buffering=1)
sys.stdout = LOG
sys.stderr = LOG
print(f"\n--- iniciado em {time.strftime('%d/%m/%Y %H:%M:%S')} ---")

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B
WM_APP = 0x8000
WM_TRAY = WM_APP + 1
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x1, 0x2, 0x4, 0x10
NIIF_INFO = 0x1
MF_STRING, MF_SEPARATOR, MF_GRAYED, MF_CHECKED = 0x0, 0x800, 0x1, 0x8
TPM_RIGHTBUTTON, TPM_RETURNCMD, TPM_NONOTIFY = 0x2, 0x100, 0x80
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
IDI_APPLICATION = 32512
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x2


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND), ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT), ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128), ("dwState", wintypes.DWORD), ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256), ("uVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64), ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", GUID), ("hBalloonIcon", wintypes.HICON)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT), ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM), ("time", wintypes.DWORD), ("pt", POINT)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
user32.LoadImageW.restype = wintypes.HANDLE
user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPVOID]
user32.LoadIconW.restype = wintypes.HICON
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                  wintypes.HWND, wintypes.LPVOID]
user32.TrackPopupMenu.restype = ctypes.c_int
user32.DestroyMenu.argtypes = [wintypes.HMENU]
user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.RegisterWindowMessageW.argtypes = [wintypes.LPCWSTR]
user32.RegisterWindowMessageW.restype = wintypes.UINT
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE
user32.MessageBoxW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.UINT]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

# ------------------------------------------------------------------ servidor

import server  # noqa: E402  (precisa vir depois do ajuste de sys.path)

PORT = server.PORT
httpd = None


def start_server() -> str | None:
    """Inicia o servidor numa thread. Devolve mensagem de erro, se houver."""
    global httpd
    try:
        httpd = server.ThreadingHTTPServer(("0.0.0.0", PORT), server.Handler)
    except OSError as exc:
        return f"A porta {PORT} já está em uso ({exc}). Talvez o Tela Tablet já esteja aberto."
    for monitor in (server.battery_monitor, server.media_monitor):
        try:
            monitor.start()
        except Exception:
            traceback.print_exc()
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    print(f"Servidor na porta {PORT}. Tablet: http://{server.local_ip()}:{PORT}")
    return None


def tablet_address() -> str:
    return f"http://{server.local_ip()}:{PORT}"


def open_panel() -> None:
    url = f"http://127.0.0.1:{PORT}"
    for base in (os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        edge = Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if base and edge.exists():
            subprocess.Popen([str(edge), f"--app={url}"], creationflags=0x08000000)
            return
    webbrowser.open(url)


def copy_to_clipboard(text: str) -> None:
    if not user32.OpenClipboard(None):
        return
    try:
        user32.EmptyClipboard()
        data = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(data)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        ptr = kernel32.GlobalLock(handle)
        ctypes.memmove(ptr, data, size)
        kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(CF_UNICODETEXT, handle)
    finally:
        user32.CloseClipboard()


# ------------------------------------------------ iniciar com o Windows

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "TelaTablet"


def startup_command() -> str:
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else exe}" "{ROOT / "tray.py"}" --sem-painel'


def startup_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
            return True
    except OSError:
        return False


def set_startup(enabled: bool) -> None:
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except OSError:
                pass


# ------------------------------------------------------------------ ícone

ID_OPEN, ID_COPY, ID_FOLDER, ID_STARTUP, ID_QUIT, ID_ADDRESS = 1, 2, 3, 4, 5, 6
hwnd = None
nid = NOTIFYICONDATAW()
TASKBAR_CREATED = user32.RegisterWindowMessageW("TaskbarCreated")


def load_icon():
    path = ROOT / "tela_tablet.ico"
    if path.exists():
        icon = user32.LoadImageW(None, str(path), IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if icon:
            return icon
    return user32.LoadIconW(None, ctypes.c_void_p(IDI_APPLICATION))


def add_icon(balloon: str | None = None) -> None:
    nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    nid.hWnd = hwnd
    nid.uID = 1
    nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    nid.uCallbackMessage = WM_TRAY
    nid.hIcon = load_icon()
    nid.szTip = f"Tela Tablet — {tablet_address()}"[:127]
    shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
    if balloon:
        nid.uFlags = NIF_INFO
        nid.szInfoTitle = "Tela Tablet rodando"
        nid.szInfo = balloon[:255]
        nid.dwInfoFlags = NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))


def show_menu() -> None:
    menu = user32.CreatePopupMenu()
    user32.AppendMenuW(menu, MF_STRING, ID_OPEN, "Abrir painel")
    user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
    user32.AppendMenuW(menu, MF_STRING | MF_GRAYED, ID_ADDRESS, f"Tablet: {tablet_address()}")
    user32.AppendMenuW(menu, MF_STRING, ID_COPY, "Copiar endereço do tablet")
    user32.AppendMenuW(menu, MF_STRING, ID_FOLDER, "Abrir pasta do projeto")
    user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if startup_enabled() else 0), ID_STARTUP, "Iniciar com o Windows")
    user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
    user32.AppendMenuW(menu, MF_STRING, ID_QUIT, "Sair")
    pt = POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    user32.SetForegroundWindow(hwnd)
    choice = user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON | TPM_RETURNCMD | TPM_NONOTIFY, pt.x, pt.y, 0, hwnd, None)
    user32.DestroyMenu(menu)
    try:
        if choice == ID_OPEN:
            open_panel()
        elif choice == ID_COPY:
            copy_to_clipboard(tablet_address())
        elif choice == ID_FOLDER:
            os.startfile(str(ROOT))
        elif choice == ID_STARTUP:
            set_startup(not startup_enabled())
        elif choice == ID_QUIT:
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    except Exception:
        traceback.print_exc()


@WNDPROC
def wnd_proc(h, msg, wparam, lparam):
    try:
        if msg == WM_TRAY:
            event = lparam & 0xFFFF
            if event == WM_LBUTTONUP:
                open_panel()
            elif event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                show_menu()
            return 0
        if msg == TASKBAR_CREATED and TASKBAR_CREATED:
            add_icon()  # o Explorer reiniciou: recoloca o ícone
            return 0
        if msg == WM_CLOSE:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            user32.DestroyWindow(h)
            return 0
        if msg == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
    except Exception:
        traceback.print_exc()
    return user32.DefWindowProcW(h, msg, wparam, lparam)


def main() -> None:
    global hwnd
    error = start_server()
    if error:
        print(error)
        # Já tem outro aberto: só abre o painel e sai
        open_panel()
        return
    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW()
    wc.lpfnWndProc = wnd_proc
    wc.hInstance = hinst
    wc.lpszClassName = "TelaTabletTray"
    user32.RegisterClassW(ctypes.byref(wc))
    hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "Tela Tablet", 0, 0, 0, 0, 0, None, None, hinst, None)
    add_icon(f"Tablet: {tablet_address()}  ·  clique no ícone para abrir o painel")
    if "--sem-painel" not in sys.argv:
        open_panel()
    msg = MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))
    if httpd:
        threading.Thread(target=httpd.shutdown, daemon=True).start()
    print("Encerrado.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        user32.MessageBoxW(None, "O Tela Tablet não conseguiu iniciar. Veja data\\tray.log.", "Tela Tablet", 0x10)
