"""Helpers to launch and stop Streamlit from Python scripts.

Usage:
    from cptcopro.utils.streamlit_launcher import start_streamlit, stop_streamlit

    p = start_streamlit(app_path="src/cptcopro/Affichage_Stream.py", port=8501)
    # ... do other work ...
    stop_streamlit(p)

The functions use `sys.executable -m streamlit run` to ensure the same venv
is used. On Windows a new process group is created to allow sending
CTRL_BREAK_EVENT for graceful shutdown.

When running from a PyInstaller bundle, Streamlit is launched directly in-process
using streamlit.web.bootstrap.run().
"""
from __future__ import annotations

import os
import sys
import signal
import subprocess
import threading
import webbrowser
from typing import Optional
from typing import Dict, Any
import socket
import logging

# map pid -> creation flags used when launching the process. Stored here
# instead of attaching attributes to the Popen object (typing/privilege issues).
_PROC_CREATION_FLAGS: Dict[int, Any] = {}
# pid -> open file object for redirected stdout/stderr. Kept so we can close on stop.
_LOG_FILE_HANDLES: Dict[int, Any] = {}

# module logger
_LOG = logging.getLogger(__name__)


def _load_streamlit_config_toml(config_toml_path: str) -> dict:
    """Load and parse a Streamlit config.toml file.
    
    Args:
        config_toml_path: Path to the config.toml file.
        
    Returns:
        Parsed config dict, or empty dict on error.
    """
    if not os.path.isfile(config_toml_path):
        return {}
    
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore[import-not-found]
    
    try:
        with open(config_toml_path, "rb") as f:
            config_data = tomllib.load(f)
        _LOG.info(f"Loaded config from {config_toml_path}")
        return config_data
    except Exception as e:
        _LOG.warning(f"Could not load config.toml: {e}")
        return {}


def is_pyinstaller_bundle() -> bool:
    """Check if running from a PyInstaller bundle."""
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def _get_bundled_app_path(app_path: str) -> str:
    """Get the correct path for the app when running from PyInstaller bundle."""
    if is_pyinstaller_bundle():
        # In PyInstaller, files are extracted to sys._MEIPASS
        base_path = sys._MEIPASS
        # The app should be in cptcopro/ directory
        if "Affichage_Stream.py" in app_path:
            bundled_path = os.path.join(base_path, "cptcopro", "Affichage_Stream.py")
            if os.path.exists(bundled_path):
                return bundled_path
        # Fallback: try the path as-is relative to _MEIPASS
        alt_path = os.path.join(base_path, app_path)
        if os.path.exists(alt_path):
            return alt_path
    return app_path


def start_streamlit_inprocess(
    app_path: str = "src/cptcopro/Affichage_Stream.py",
    port: int = 8501,
    host: str = "127.0.0.1",
    open_browser: bool = True,
) -> None:
    """Start Streamlit in-process (for PyInstaller bundles).
    
    This function runs Streamlit directly in the main thread to avoid
    the "signal only works in main thread" error.
    
    Note: This function blocks and does not return until Streamlit exits.
    """
    # Set environment variables BEFORE importing streamlit modules
    # This is critical because streamlit reads these on module import
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    
    from streamlit.web import bootstrap
    import streamlit.config as st_config
    
    # Get the correct path for the bundled app
    resolved_path = _get_bundled_app_path(app_path)
    
    if not os.path.exists(resolved_path):
        raise FileNotFoundError(
            f"Fichier Streamlit non trouvé: {resolved_path}\n"
            f"Chemin original: {app_path}\n"
            f"MEIPASS: {getattr(sys, '_MEIPASS', 'N/A')}"
        )
    
    # Configure Streamlit config directory for PyInstaller bundle
    if is_pyinstaller_bundle():
        base_path = sys._MEIPASS
        streamlit_config_dir = os.path.join(base_path, "cptcopro", ".streamlit")
        config_toml_path = os.path.join(streamlit_config_dir, "config.toml")
        if os.path.isdir(streamlit_config_dir):
            _LOG.info(f"Streamlit config directory: {streamlit_config_dir}")
            # Load config.toml and apply settings via helper
            config_data = _load_streamlit_config_toml(config_toml_path)
            # Apply theme settings from config.toml
            if "theme" in config_data:
                for key, value in config_data["theme"].items():
                    st_config.set_option(f"theme.{key}", value)
                    _LOG.info(f"Applied theme.{key} = {value}")
            # Apply browser settings
            if "browser" in config_data:
                for key, value in config_data["browser"].items():
                    st_config.set_option(f"browser.{key}", value)
    
    _LOG.info(f"Lancement Streamlit in-process: {resolved_path}")
    
    # Find a free port if the requested one is in use
    used_port = port
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((host, port))
    except OSError:
        used_port = _find_free_port(port, host=host, max_tries=50)
        _LOG.warning("Port %d indisponible, utilisation du port %d", port, used_port)
    
    # CRITICAL: Force production mode by directly setting the config option
    # This prevents Streamlit from trying to connect to Node dev server on port 3000
    try:
        st_config.set_option("global.developmentMode", False)
        _LOG.info("Forced global.developmentMode = False")
    except Exception as e:
        _LOG.warning(f"Could not set developmentMode directly: {e}")
    
    os.environ["STREAMLIT_SERVER_PORT"] = str(used_port)
    os.environ["STREAMLIT_SERVER_ADDRESS"] = host
    
    # Open browser manually before starting (Streamlit headless mode won't open it)
    if open_browser:
        url = f"http://{host}:{used_port}"
        threading.Timer(2.0, lambda: webbrowser.open(url)).start()
    
    # Use bootstrap.run() which is designed to be called from main thread
    # This avoids the "signal only works in main thread" error
    flag_options = {
        "global.developmentMode": False,
        "server.port": used_port,
        "server.address": host,
        "server.headless": True,
        "server.fileWatcherType": "none",
        "browser.gatherUsageStats": False,
        "runner.fastReruns": False,
    }
    
    # Load theme options from config.toml if in PyInstaller bundle
    if is_pyinstaller_bundle():
        base_path = sys._MEIPASS
        config_toml_path = os.path.join(base_path, "cptcopro", ".streamlit", "config.toml")
        config_data = _load_streamlit_config_toml(config_toml_path)
        # Add theme settings to flag_options
        if "theme" in config_data:
            for key, value in config_data["theme"].items():
                flag_options[f"theme.{key}"] = value
                _LOG.info(f"Added to flag_options: theme.{key} = {value}")
    
    try:
        bootstrap.run(resolved_path, False, [], flag_options)
    except SystemExit:
        pass  # Streamlit calls sys.exit() on shutdown
    except Exception as e:
        _LOG.error(f"Erreur Streamlit: {e}")
        raise


def _find_free_port(start_port: int, host: str = "127.0.0.1", max_tries: int = 20) -> int:
    """Find a free TCP port starting from `start_port` by probing sequentially.

    Returns the first free port found within `max_tries` attempts, otherwise
    raises a RuntimeError.
    """
    for offset in range(max_tries):
        p = start_port + offset
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind((host, p))
                return p
            except OSError:
                continue
    raise RuntimeError(f"Aucun port libre trouvé à partir de {start_port} (essais={max_tries})")


def start_streamlit(
    app_path: str = "src/cptcopro/Affichage_Stream.py",
    python_executable: Optional[str] = None,
    port: int = 8501,
    host: str = "127.0.0.1",
    show_console: bool = True,
    open_browser: bool = True,
    cols: Optional[int] = None,
    lines: Optional[int] = None,
    stdout: Optional[int] = subprocess.DEVNULL,
    stderr: Optional[int] = subprocess.DEVNULL,
    use_cmd_start: bool = False,
    log_file: Optional[str] = None,
) -> subprocess.Popen:
    """Start Streamlit and return the Popen object.

    By default `show_console=True` opens a visible Windows console. When
    `show_console` is True on Windows, a new console window is created.    
    
    Start Streamlit and return the Popen object.

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
        try:
            check = subprocess.run(
                [
                    python_exe,
                    "-c",
                    "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('streamlit') else 1)",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Vérification du module 'streamlit' dans '{python_exe}' échouée : timeout dépassé."
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
    # If the requested port is already in use, attempt to find a nearby free
    # port to avoid the "Port ... is already in use" Streamlit error.
    used_port = port
    try:
        # probe the port by attempting to bind; if binding fails, port is in use
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            probe.bind((host, port))
    except OSError:
        try:
            used_port = _find_free_port(port, host=host, max_tries=50)
            _LOG.warning("Port %d indisponible, utilisation du port %d à la place", port, used_port)
        except RuntimeError as re:
            # unable to find free port - re-raise as runtime error for caller
            raise RuntimeError(str(re))

    cmd = [
        python_exe,
        "-m",
        "streamlit",
        "run",
        app_path,
        "--server.port",
        str(used_port),
        "--server.address",
        host,
    ]

    # Prepare optional log file for redirection. If provided and we launch
    # without `use_cmd_start`, we will pass the open file handles to Popen.
    # If `use_cmd_start` is used, we embed redirection into the cmdline.
    log_f = None
    if log_file:
        log_path = os.path.abspath(log_file)
    else:
        log_path = None

    # If user requests a visible console, do not redirect stdout/stderr by default
    # and open a new console window on Windows. Otherwise keep defaults.
    if show_console:
        # When requesting a visible console, prefer to open a new console and
        # set its size on Windows using `mode con` before launching Streamlit.
        use_stdout = None
        use_stderr = None
        if os.name == "nt":
            if use_cmd_start:
                # Use `cmd /c start` to force a new window. Note: the returned Popen
                # is the cmd process which will exit; stopping the Streamlit process
                # later may require manual intervention (closing the window).
                # Use cmd /k inside the new window so the window stays open
                # even if the Streamlit process exits or errors. This helps
                # with debugging when the console was opening-and-closing.
                cmdline = (
                    f'"{python_exe}" -m streamlit run "{app_path}" '
                    f'--server.port {port} --server.address {host}'
                )
                # Append an echo + pause to keep the new console open after
                # Streamlit exits so the user can read errors. This is helpful
                # for debugging when the window was opening-and-closing.
                # If a log path is requested, redirect stdout/stderr inside the
                # launched cmd so the output is written to the file even if the
                # console is closed by the user.
                if log_path:
                    # Ensure parent dir exists
                    os.makedirs(os.path.dirname(log_path), exist_ok=True) if os.path.dirname(log_path) else None
                    redirected = f'{cmdline} > "{log_path}" 2>&1'
                else:
                    redirected = cmdline

                debug_wrapper = (
                    redirected
                    + " & echo. & echo --- Streamlit process terminated --- & echo Exit code=%ERRORLEVEL% & echo Log file="
                    + (f'"{log_path}"' if log_path else 'none')
                    + " & pause"
                )
                start_cmd = [
                    "cmd",
                    "/c",
                    "start",
                    "Streamlit",
                    "cmd",
                    "/k",
                    debug_wrapper,
                ]
                proc = subprocess.Popen(start_cmd, stdout=use_stdout, stderr=use_stderr)
                try:
                    _PROC_CREATION_FLAGS[proc.pid] = "CMD_START"
                except Exception:
                    pass
            else:
                # Open a new console and run Streamlit directly using the python executable.
                # Use list args to avoid cmd quoting issues.
                proc = subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NEW_CONSOLE,
                    stdout=use_stdout,
                    stderr=use_stderr,
                )
                # record creation flags so stop_streamlit can choose the correct shutdown
                try:
                    _PROC_CREATION_FLAGS[proc.pid] = subprocess.CREATE_NEW_CONSOLE
                except Exception:
                    pass
        else:
            # Non-Windows: fallback to previous visible-start behaviour
            proc = subprocess.Popen(
                cmd, start_new_session=True, stdout=use_stdout, stderr=use_stderr
            )
            try:
                _PROC_CREATION_FLAGS[proc.pid] = None
            except Exception:
                pass
    else:
        if os.name == "nt":
            # When not showing console, redirect stdout/stderr to the provided
            # destinations. If a log_path was provided, open it and pass the
            # file handle so we capture Streamlit output.
            if log_path:
                os.makedirs(os.path.dirname(log_path), exist_ok=True) if os.path.dirname(log_path) else None
                log_f = open(log_path, "a", encoding="utf-8", buffering=1)
                proc = subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    stdout=log_f,
                    stderr=log_f,
                )
            else:
                proc = subprocess.Popen(
                    cmd,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                    stdout=stdout,
                    stderr=stderr,
                )
            try:
                _PROC_CREATION_FLAGS[proc.pid] = subprocess.CREATE_NEW_PROCESS_GROUP
                if log_f is not None:
                    _LOG_FILE_HANDLES[proc.pid] = log_f
            except Exception:
                pass
        else:
            if log_path:
                os.makedirs(os.path.dirname(log_path), exist_ok=True) if os.path.dirname(log_path) else None
                log_f = open(log_path, "a", encoding="utf-8", buffering=1)
                proc = subprocess.Popen(
                    cmd, start_new_session=True, stdout=log_f, stderr=log_f
                )
                try:
                    _PROC_CREATION_FLAGS[proc.pid] = None
                    _LOG_FILE_HANDLES[proc.pid] = log_f
                except Exception:
                    pass
            else:
                proc = subprocess.Popen(
                    cmd, start_new_session=True, stdout=stdout, stderr=stderr
                )
                try:
                    _PROC_CREATION_FLAGS[proc.pid] = None
                except Exception:
                    pass

    # Do not call webbrowser.open() here. Streamlit itself opens the browser
    # by default which was causing duplicate tabs (launcher + Streamlit both
    # opening). If you want to suppress Streamlit opening the browser, use
    # Streamlit's own config or pass `--server.headless true` in a future
    # change; for now we rely on Streamlit's default behaviour.
    # store logfile handle for non-cmd-start cases so we can close it on stop
    try:
        if log_f is not None and proc is not None:
            _LOG_FILE_HANDLES[proc.pid] = log_f
    except Exception:
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
            # Choose shutdown method based on how the process was started.
            # We recorded the creation flags in `_PROC_CREATION_FLAGS` keyed by pid.
            creation_flags = _PROC_CREATION_FLAGS.pop(proc.pid, None)
            if creation_flags == subprocess.CREATE_NEW_PROCESS_GROUP:
                # send CTRL_BREAK_EVENT to the process group for graceful shutdown
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
                    # fallback to terminate
                    proc.terminate()
            elif creation_flags == subprocess.CREATE_NEW_CONSOLE:
                # process has its own console - CTRL events won't reach it from here
                # use terminate() for graceful shutdown
                try:
                    proc.terminate()
                except Exception:
                    pass
            else:
                # unknown creation flags: try graceful signals first, then terminate
                try:
                    proc.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
                    try:
                        proc.terminate()
                    except Exception:
                        pass
        else:
            proc.terminate()
        proc.wait(timeout=timeout)
    except Exception:
        if force:
            try:
                proc.kill()
            except Exception:
                pass
    finally:
        # Close any logfile handles we opened for this pid
        try:
            f = _LOG_FILE_HANDLES.pop(proc.pid, None)
            if f is not None:
                try:
                    f.close()
                except Exception:
                    pass
        except Exception:
            pass


__all__ = ["start_streamlit", "stop_streamlit"]


def _parse_cli_args() -> dict:
    import argparse

    parser = argparse.ArgumentParser(
        description="Lance Streamlit (par défaut ouvre une console). Utilisez --no-console pour ne PAS ouvrir la console."
    )
    parser.add_argument("--app-path", default="src/cptcopro/Affichage_Stream.py")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--no-console", dest="no_console", action="store_true",
                        help="Ne pas ouvrir de console visible (redirige stdout/stderr).")
    parser.add_argument("--no-browser", dest="no_browser", action="store_true",
                        help="Ne pas ouvrir automatiquement le navigateur web.")
    parser.add_argument("--cols", type=int, default=None, help="Colonnes console (Windows)")
    parser.add_argument("--lines", type=int, default=None, help="Lignes console (Windows)")
    parser.add_argument("--use-cmd-start", dest="use_cmd_start", action="store_true",
                        help="Sur Windows, utilise `cmd /c start` pour forcer une nouvelle fenêtre (fallback).")
    parser.add_argument("--log-file", dest="log_file", default=None,
                        help="Fichier dans lequel rediriger stdout/stderr de Streamlit (ex: streamlit_stdout.log)")
    return vars(parser.parse_args())


if __name__ == "__main__":
    # Comportement CLI : par défaut la console est visible. Utiliser --no-console pour la désactiver.
    args = _parse_cli_args()
    show_console = not bool(args["no_console"])
    open_browser = not bool(args["no_browser"])
    use_cmd_start = bool(args["use_cmd_start"])

    try:
        proc = start_streamlit(
            app_path=args["app_path"],
            port=args["port"],
            host=args["host"],
            show_console=show_console,
            open_browser=open_browser,
            cols=args["cols"],
            lines=args["lines"],
            use_cmd_start=use_cmd_start,
            log_file=args.get("log_file"),
        )
        print(f"Streamlit lancé (pid={proc.pid}), show_console={show_console}")
        # Attendre tant que le processus tourne; quitter proprement sur Ctrl-C
        try:
            proc.wait()
        except KeyboardInterrupt:
            print("Interruption reçue, arrêt de Streamlit...")
            stop_streamlit(proc)
    except Exception as e:
        print(f"Erreur lancement Streamlit: {e}")