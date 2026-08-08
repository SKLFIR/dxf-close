# -*- coding: utf-8 -*-
"""Создание ярлыка на рабочем столе: .lnk на Windows, .app на macOS, .desktop на Linux."""
import os
import plistlib
import shutil
import stat
import subprocess
import sys

APP_NAME = "Замыкание контуров DXF"
BUNDLE_ID = "ru.sklfir.dxfclose"


def assets_dir():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")


def _gui_python():
    """Интерпретатор для запуска без консольного окна."""
    exe = sys.executable
    if sys.platform == "win32":
        cand = os.path.join(os.path.dirname(exe), "pythonw.exe")
        if os.path.exists(cand):
            return cand
    return exe


# ------------------------------------------------------------------ Windows
def _desktop_windows():
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
            capture_output=True, text=True, timeout=30)
        p = out.stdout.strip()
        if p and os.path.isdir(p):
            return p
    except Exception:
        pass
    return os.path.join(os.path.expanduser("~"), "Desktop")


def _make_windows(desktop):
    link = os.path.join(desktop, APP_NAME + ".lnk")
    icon = os.path.join(assets_dir(), "icon.ico")
    ps = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(%s);"
        "$s.TargetPath = %s;"
        "$s.Arguments = '-m dxf_close';"
        "$s.WorkingDirectory = %s;"
        "$s.IconLocation = %s;"
        "$s.Description = 'Замыкание контуров DXF';"
        "$s.Save()"
    ) % (_psq(link), _psq(_gui_python()), _psq(os.path.expanduser("~")), _psq(icon))
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                   capture_output=True, text=True)
    return link


def _psq(s):
    """Строка в одинарных кавычках PowerShell."""
    return "'" + s.replace("'", "''") + "'"


# ------------------------------------------------------------------ macOS
def _make_macos(desktop):
    app = os.path.join(desktop, APP_NAME + ".app")
    if os.path.exists(app):
        shutil.rmtree(app)
    macos_dir = os.path.join(app, "Contents", "MacOS")
    res_dir = os.path.join(app, "Contents", "Resources")
    os.makedirs(macos_dir)
    os.makedirs(res_dir)

    launcher = os.path.join(macos_dir, "dxf-close")
    with open(launcher, "w", encoding="utf-8") as f:
        f.write('#!/bin/sh\nexec "%s" -m dxf_close "$@"\n' % _gui_python())
    os.chmod(launcher, os.stat(launcher).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    icns = os.path.join(assets_dir(), "icon.icns")
    if os.path.exists(icns):
        shutil.copy(icns, os.path.join(res_dir, "icon.icns"))

    info = {
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleExecutable": "dxf-close",
        "CFBundleIdentifier": BUNDLE_ID,
        "CFBundleIconFile": "icon.icns",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "1.0",
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSMinimumSystemVersion": "10.13",
        "NSHighResolutionCapable": True,
    }
    with open(os.path.join(app, "Contents", "Info.plist"), "wb") as f:
        plistlib.dump(info, f)

    # заставить Finder перечитать иконку
    subprocess.run(["touch", app], check=False)
    return app


# ------------------------------------------------------------------ Linux
def _make_linux(desktop):
    path = os.path.join(desktop, "dxf-close.desktop")
    png = os.path.join(assets_dir(), "icon_256.png")
    with open(path, "w", encoding="utf-8") as f:
        f.write(
            "[Desktop Entry]\nType=Application\nName=%s\n"
            "Exec=\"%s\" -m dxf_close %%f\nIcon=%s\nTerminal=false\nCategories=Graphics;\n"
            % (APP_NAME, _gui_python(), png))
    os.chmod(path, 0o755)
    return path


# ------------------------------------------------------------------ общее
def create(desktop=None):
    """Создаёт ярлык и возвращает путь к нему."""
    if desktop is None:
        if sys.platform == "win32":
            desktop = _desktop_windows()
        else:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if not os.path.isdir(desktop):
        os.makedirs(desktop, exist_ok=True)

    if sys.platform == "win32":
        return _make_windows(desktop)
    if sys.platform == "darwin":
        return _make_macos(desktop)
    return _make_linux(desktop)
