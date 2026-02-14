"""Локальная web-панель конфигурации и управления запуском Noty."""

from __future__ import annotations

import html
import json
import os
import secrets
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import yaml

try:
    from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
    from fastapi.responses import HTMLResponse, RedirectResponse
    from fastapi.security import HTTPBasic, HTTPBasicCredentials

    FASTAPI_AVAILABLE = True
except ImportError:  # pragma: no cover - fallback для окружений без fastapi
    FASTAPI_AVAILABLE = False
    Depends = lambda dependency=None: None

    class _DummyApp:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def get(self, *_args, **_kwargs):
            return lambda fn: fn

        def post(self, *_args, **_kwargs):
            return lambda fn: fn

    class HTTPException(Exception):
        pass

    class HTTPBasicCredentials:  # type: ignore[override]
        def __init__(self, username: str = "", password: str = "") -> None:
            self.username = username
            self.password = password

    class HTTPBasic:  # type: ignore[override]
        def __call__(self):
            return None

    class Request:  # type: ignore[override]
        pass

    class RedirectResponse:  # type: ignore[override]
        def __init__(self, *args, **kwargs) -> None:
            self.args = args
            self.kwargs = kwargs

    class HTMLResponse(str):
        pass

    class _Status:
        HTTP_401_UNAUTHORIZED = 401

    status = _Status()
    Form = lambda default=None: default
    FastAPI = _DummyApp


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = PROJECT_ROOT / "noty" / "config"
ENV_PATH = CONFIG_DIR / ".env"
BOT_CONFIG_PATH = CONFIG_DIR / "bot_config.yaml"
PERSONA_CONFIG_PATH = CONFIG_DIR / "persona_prompt_config.json"
API_KEYS_PATH = CONFIG_DIR / "api_keys.json"


security = HTTPBasic()


@dataclass
class RuntimePaths:
    env_path: Path
    bot_config_path: Path
    persona_config_path: Path
    api_keys_path: Path


PATHS = RuntimePaths(
    env_path=ENV_PATH,
    bot_config_path=BOT_CONFIG_PATH,
    persona_config_path=PERSONA_CONFIG_PATH,
    api_keys_path=API_KEYS_PATH,
)


class NotyProcessManager:
    """Управление жизненным циклом отдельного процесса Noty."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None
        self._lock = threading.RLock()

    def start(self, mode: str | None = None) -> str:
        with self._lock:
            if self.is_running():
                return "already_running"

            cmd = [sys.executable, "main.py"]
            if mode:
                cmd.extend(["--mode", mode])

            self._process = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            return "started"

    def stop(self) -> str:
        with self._lock:
            if not self.is_running():
                return "already_stopped"

            assert self._process is not None
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=3)
            finally:
                self._process = None
            return "stopped"

    def restart(self, mode: str | None = None) -> str:
        with self._lock:
            was_running = self.is_running()
            if was_running:
                self.stop()
            self.start(mode=mode)
            return "restarted" if was_running else "started"

    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def status(self) -> dict[str, Any]:
        process = self._process
        return {
            "running": self.is_running(),
            "pid": process.pid if process and self.is_running() else None,
        }


PROCESS_MANAGER = NotyProcessManager()


def _safe_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as tmp:
        tmp.write(payload)
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def _read_env(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def _write_env(path: Path, env_data: dict[str, str]) -> None:
    body = "\n".join(f"{key}={value}" for key, value in sorted(env_data.items())) + "\n"
    _safe_write(path, body)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    _safe_write(path, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_json(path: Path, data: dict[str, Any]) -> None:
    _safe_write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def _get_panel_password() -> str:
    env_data = _read_env(PATHS.env_path)
    return env_data.get("LOCAL_PANEL_PASSWORD", "change-me")


def _verify_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    password = _get_panel_password()
    is_valid_user = secrets.compare_digest(credentials.username, "admin")
    is_valid_password = secrets.compare_digest(credentials.password, password)
    if not (is_valid_user and is_valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _compose_view_model() -> dict[str, Any]:
    env_data = _read_env(PATHS.env_path)
    bot_cfg = _load_yaml(PATHS.bot_config_path)
    persona_cfg = _load_json(PATHS.persona_config_path)
    keys_cfg = _load_json(PATHS.api_keys_path)

    transport = bot_cfg.get("transport", {})
    llm_cfg = bot_cfg.get("llm", {})
    mem0_enabled = env_data.get("MEM0_ENABLED", "false")

    policy = persona_cfg.get("persona_adaptation_policy", {})

    return {
        "vk_token": transport.get("vk_token", ""),
        "vk_group_id": transport.get("vk_group_id", ""),
        "llm_backend": llm_cfg.get("backend", "openai"),
        "openrouter_api_key": env_data.get("OPENROUTER_API_KEY", ""),
        "sqlite_path": env_data.get("SQLITE_PATH", "./noty/data/noty.db"),
        "mem0_enabled": mem0_enabled,
        "mem0_api_key": env_data.get("MEM0_API_KEY", ""),
        "qdrant_url": env_data.get("QDRANT_URL", ""),
        "qdrant_api_key": env_data.get("QDRANT_API_KEY", ""),
        "local_panel_password": env_data.get("LOCAL_PANEL_PASSWORD", "change-me"),
        "prompt_config_json": json.dumps(persona_cfg, ensure_ascii=False, indent=2),
        "personality_version": policy.get("version", "n/a"),
        "personality_reason": policy.get("reason", "n/a"),
        "service_status": PROCESS_MANAGER.status(),
        "api_keys_count": len(keys_cfg.get("openrouter_keys", [])),
    }


def save_runtime_settings(form_data: dict[str, str]) -> None:
    env_data = _read_env(PATHS.env_path)
    env_data["OPENROUTER_API_KEY"] = form_data.get("openrouter_api_key", "").strip()
    env_data["SQLITE_PATH"] = form_data.get("sqlite_path", "./noty/data/noty.db").strip()
    env_data["MEM0_ENABLED"] = form_data.get("mem0_enabled", "false").strip().lower()
    env_data["MEM0_API_KEY"] = form_data.get("mem0_api_key", "").strip()
    env_data["QDRANT_URL"] = form_data.get("qdrant_url", "").strip()
    env_data["QDRANT_API_KEY"] = form_data.get("qdrant_api_key", "").strip()

    panel_password = form_data.get("local_panel_password", "").strip()
    if panel_password:
        env_data["LOCAL_PANEL_PASSWORD"] = panel_password

    _write_env(PATHS.env_path, env_data)

    bot_cfg = _load_yaml(PATHS.bot_config_path)
    transport = bot_cfg.setdefault("transport", {})
    llm_cfg = bot_cfg.setdefault("llm", {})
    transport["vk_token"] = form_data.get("vk_token", "").strip()
    transport["vk_group_id"] = int(form_data.get("vk_group_id", "0") or 0)
    llm_cfg["backend"] = form_data.get("llm_backend", "openai").strip() or "openai"
    _save_yaml(PATHS.bot_config_path, bot_cfg)

    prompt_config_raw = form_data.get("prompt_config_json", "{}")
    prompt_config = json.loads(prompt_config_raw)
    _save_json(PATHS.persona_config_path, prompt_config)

    openrouter_key = env_data.get("OPENROUTER_API_KEY", "")
    keys_payload = {"openrouter_keys": [openrouter_key] if openrouter_key else []}
    _save_json(PATHS.api_keys_path, keys_payload)


app = FastAPI(title="Noty Local Config Panel")


@app.get("/", response_class=HTMLResponse)
def index(_: str = Depends(_verify_auth)) -> str:
    vm = _compose_view_model()
    running = "🟢 Запущен" if vm["service_status"]["running"] else "🔴 Остановлен"

    checked_true = "checked" if vm["mem0_enabled"] == "true" else ""
    checked_false = "checked" if vm["mem0_enabled"] != "true" else ""

    safe = {key: html.escape(str(value), quote=True) for key, value in vm.items()}

    return f"""
    <html>
    <head><meta charset='utf-8'><title>Noty Panel</title></head>
    <body style='font-family: sans-serif; max-width: 920px; margin: 20px auto;'>
      <h1>Noty локальная панель</h1>
      <p><b>Статус сервиса:</b> {running}</p>
      <p><b>Personality version:</b> {safe['personality_version']} | <b>reason:</b> {safe['personality_reason']}</p>
      <p><b>OpenRouter ключей:</b> {safe['api_keys_count']}</p>

      <form method='post' action='/save'>
        <h2>Основные параметры</h2>
        <label>VK token<br><input name='vk_token' style='width:100%' value='{safe['vk_token']}'></label><br><br>
        <label>VK group id<br><input name='vk_group_id' style='width:100%' value='{safe['vk_group_id']}'></label><br><br>
        <label>LLM backend<br><input name='llm_backend' style='width:100%' value='{safe['llm_backend']}'></label><br><br>
        <label>OpenRouter API key<br><input name='openrouter_api_key' style='width:100%' value='{safe['openrouter_api_key']}'></label><br><br>
        <label>SQLite path<br><input name='sqlite_path' style='width:100%' value='{safe['sqlite_path']}'></label><br><br>

        <h2>Mem0 / Qdrant</h2>
        <label><input type='radio' name='mem0_enabled' value='true' {checked_true}> Mem0 включён</label>
        <label><input type='radio' name='mem0_enabled' value='false' {checked_false}> Mem0 выключен</label><br><br>
        <label>Mem0 API key<br><input name='mem0_api_key' style='width:100%' value='{safe['mem0_api_key']}'></label><br><br>
        <label>Qdrant URL<br><input name='qdrant_url' style='width:100%' value='{safe['qdrant_url']}'></label><br><br>
        <label>Qdrant API key<br><input name='qdrant_api_key' style='width:100%' value='{safe['qdrant_api_key']}'></label><br><br>

        <h2>Безопасность панели</h2>
        <label>Новый пароль панели (оставь пустым чтобы не менять)<br>
        <input name='local_panel_password' type='password' style='width:100%'></label><br><br>

        <h2>Редактор prompt-конфига (JSON)</h2>
        <textarea name='prompt_config_json' rows='18' style='width:100%'>{safe['prompt_config_json']}</textarea><br><br>

        <button type='submit'>Сохранить</button>
      </form>

      <hr>
      <form method='post' action='/service/start' style='display:inline-block'><button>Запустить Noti</button></form>
      <form method='post' action='/service/stop' style='display:inline-block'><button>Остановить Noti</button></form>
      <form method='post' action='/service/reload' style='display:inline-block'><button>Перезагрузить Noti</button></form>
      <form method='get' action='/' style='display:inline-block'><button>Статус сервиса</button></form>
    </body>
    </html>
    """


@app.post("/save")
def save(
    request: Request,
    vk_token: str = Form(""),
    vk_group_id: str = Form("0"),
    llm_backend: str = Form("openai"),
    openrouter_api_key: str = Form(""),
    sqlite_path: str = Form("./noty/data/noty.db"),
    mem0_enabled: str = Form("false"),
    mem0_api_key: str = Form(""),
    qdrant_url: str = Form(""),
    qdrant_api_key: str = Form(""),
    local_panel_password: str = Form(""),
    prompt_config_json: str = Form("{}"),
    _: str = Depends(_verify_auth),
) -> RedirectResponse:
    form_data = {
        "vk_token": vk_token,
        "vk_group_id": vk_group_id,
        "llm_backend": llm_backend,
        "openrouter_api_key": openrouter_api_key,
        "sqlite_path": sqlite_path,
        "mem0_enabled": mem0_enabled,
        "mem0_api_key": mem0_api_key,
        "qdrant_url": qdrant_url,
        "qdrant_api_key": qdrant_api_key,
        "local_panel_password": local_panel_password,
        "prompt_config_json": prompt_config_json,
    }
    save_runtime_settings(form_data)

    if PROCESS_MANAGER.is_running():
        mode = _load_yaml(PATHS.bot_config_path).get("transport", {}).get("mode")
        PROCESS_MANAGER.restart(mode=mode)

    return RedirectResponse(url=str(request.url_for("index")), status_code=303)


@app.post("/service/start")
def service_start(request: Request, _: str = Depends(_verify_auth)) -> RedirectResponse:
    mode = _load_yaml(PATHS.bot_config_path).get("transport", {}).get("mode")
    PROCESS_MANAGER.start(mode=mode)
    return RedirectResponse(url=str(request.url_for("index")), status_code=303)


@app.post("/service/stop")
def service_stop(request: Request, _: str = Depends(_verify_auth)) -> RedirectResponse:
    PROCESS_MANAGER.stop()
    return RedirectResponse(url=str(request.url_for("index")), status_code=303)


@app.post("/service/reload")
def service_reload(request: Request, _: str = Depends(_verify_auth)) -> RedirectResponse:
    mode = _load_yaml(PATHS.bot_config_path).get("transport", {}).get("mode")
    PROCESS_MANAGER.restart(mode=mode)
    return RedirectResponse(url=str(request.url_for("index")), status_code=303)
