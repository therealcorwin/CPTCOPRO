"""Helpers to launch and stop Streamlit from Python scripts.

Usage:
    from cptcopro.utils.streamlit_launcher import start_streamlit, stop_streamlit

    p = start_streamlit(app_path="src/cptcopro/Affichage_Stream.py", port=8501)
    # ... do other work ...
    stop_streamlit(p)

The functions use `sys.executable -m streamlit run` to ensure the same venv
is used. On Windows a new process group is created to allow sending
CTRL_BREAK_EVENT for graceful shutdown.
"""
from __future__ import annotations

import os
import sys
import signal
import subprocess
import webbrowser
from typing import Optional


def start_streamlit(
    app_path: str = "src/cptcopro/Affichage_Stream.py",
    port: int = 8501,
    host: str = "127.0.0.1",
    python_executable: Optional[str] = None,
    open_browser: bool = True,
    show_console: bool = True,
    cols: int = 120,
    lines: int = 40,
    stdout: Optional[int] = subprocess.DEVNULL,
    stderr: Optional[int] = subprocess.DEVNULL,
) -> subprocess.Popen:
    """Start Streamlit and return the Popen object.

    By default `show_console=True` opens a visible Windows console. When
    `show_console` is True on Windows, the console size (columns x lines)
    can be set using `cols` and `lines` (uses `mode con: cols=.. lines=..`).

    - `python_executable`: path to Python to use (default: sys.executable).
    - `stdout`/`stderr`: where to redirect output (default: DEVNULL)
      (ignored when `show_console=True`).
    """
    python_exe = python_executable or sys.executable
    # Verify that `streamlit` is importable in the selected Python executable.
    # We run a small Python snippet that exits 0 if streamlit is available, 1 otherwise.
    try:
        check = subprocess.run(
            [python_exe, "-c", "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('streamlit') else 1)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise RuntimeError(
            f"L'exécutable Python spécifié n'a pas été trouvé : {python_exe}. "
            "Vérifiez le chemin ou utilisez l'option `python_executable` avec un interpréteur valide."
        )
    if check.returncode != 0:
        raise RuntimeError(
            f"Le module 'streamlit' n'est pas installé dans l'environnement Python '{python_exe}'.\n"
            "Installez-le dans cet environnement (ex. `poetry add streamlit` ou `pip install streamlit`), "
            "ou fournissez un autre interpréteur via `python_executable` (par ex. le binaire créé par Poetry)."
        )
    cmd = [
        python_exe,
        "-m",
        "streamlit",
        "run",
        app_path,
        "--server.port",
        str(port),
        "--server.address",
        host,
    ]

    # If user requests a visible console, do not redirect stdout/stderr and
    # open a new console window on Windows. Otherwise keep defaults.
    if show_console:
        # When requesting a visible console, prefer to open a new console and
        # set its size on Windows using `mode con` before launching Streamlit.
        use_stdout = None
        use_stderr = None
        if os.name == "nt":
            # Open a new console and run Streamlit directly using the python executable.
            # Use list args to avoid cmd quoting issues.
            proc = subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
                stdout=use_stdout,
                stderr=use_stderr,
            )
        else:
            # Non-Windows: fallback to previous visible-start behaviour
            proc = subprocess.Popen(
                cmd, start_new_session=True, stdout=use_stdout, stderr=use_stderr
            )
    else:
        if os.name == "nt":
            proc = subprocess.Popen(
                cmd,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                stdout=stdout,
                stderr=stderr,
            )
        else:
            proc = subprocess.Popen(
                cmd, start_new_session=True, stdout=stdout, stderr=stderr
            )

    if open_browser:
        try:
            webbrowser.open(f"http://{host}:{port}")
        except Exception:
            # best-effort opening of browser; don't raise
            pass

    return proc


def stop_streamlit(proc: subprocess.Popen, force: bool = True, timeout: int = 5) -> None:
    """Stop a Streamlit process started by `start_streamlit`.

    Tries a graceful shutdown first, then kills the process if `force` is True.
    """
    if proc is None:
        return

    try:
        if os.name == "nt":
            # send CTRL_BREAK_EVENT to the process group started with CREATE_NEW_PROCESS_GROUP
            proc.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            proc.terminate()
        proc.wait(timeout=timeout)
    except Exception:
        if force:
            try:
                proc.kill()
            except Exception:
                pass


__all__ = ["start_streamlit", "stop_streamlit"]