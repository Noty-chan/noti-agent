"""Локальная web-панель конфигурации и управления запуском Noty."""

from __future__ import annotations

import html
import json
import os
import secrets
import subprocess
import sys
import threading
import uuid
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

import yaml

try:
    from fastapi import Depends, FastAPI, Form, HTTPException, Request, status
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
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

    class JSONResponse(dict):  # type: ignore[override]
        def __init__(self, content, status_code: int = 200):
            super().__init__(content)
            self.status_code = status_code

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
RUNTIME_LOG_PATH = PROJECT_ROOT / "noty" / "data" / "logs" / "runtime" / "noty-runtime.log"
INTERACTIONS_LOG_DIR = PROJECT_ROOT / "noty" / "data" / "logs" / "interactions"
THOUGHTS_LOG_DIR = PROJECT_ROOT / "noty" / "data" / "logs" / "thoughts"
ACTIONS_LOG_DIR = PROJECT_ROOT / "noty" / "data" / "logs" / "actions"
CHAT_TRACE_LOG_PATH = PROJECT_ROOT / "noty" / "data" / "logs" / "runtime" / "noty-chat-trace.jsonl"


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
        self._log_handle: Any | None = None
        self._lock = threading.RLock()

    def start(self, mode: str | None = None) -> str:
        with self._lock:
            if self.is_running():
                return "already_running"

            cmd = [sys.executable, "main.py"]
            if mode:
                cmd.extend(["--mode", mode])

            RUNTIME_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = open(RUNTIME_LOG_PATH, "a", encoding="utf-8")
            self._log_handle.write(f"\n[{datetime.now().isoformat()}] Starting process: {' '.join(cmd)}\n")
            self._log_handle.flush()

            self._process = subprocess.Popen(
                cmd,
                cwd=PROJECT_ROOT,
                stdout=self._log_handle,
                stderr=self._log_handle,
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
                if self._log_handle:
                    self._log_handle.write(f"[{datetime.now().isoformat()}] Process stopped\n")
                    self._log_handle.flush()
                    self._log_handle.close()
                    self._log_handle = None
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


class LocalPanelChatSimulator:
    """Локальный чат-симулятор для проверки ответов Ноти через web-панель."""

    def __init__(self, history_limit: int = 30) -> None:
        self._bot: Any | None = None
        self._lock = threading.RLock()
        self._history: list[dict[str, str]] = []
        self._jobs: dict[str, dict[str, Any]] = {}
        self._history_limit = history_limit

    def _log_chat_trace(self, payload: dict[str, Any]) -> None:
        record = {
            "timestamp": datetime.now().isoformat(),
            **payload,
        }
        CHAT_TRACE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CHAT_TRACE_LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _process_event(self, request_id: str, event: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            if self._bot is None:
                self._bot = self._build_bot()
            bot = self._bot

        self._log_chat_trace(
            {
                "request_id": request_id,
                "stage": "llm_pipeline_started",
                "chat_id": event["chat_id"],
                "user_id": event["user_id"],
            }
        )
        result = bot.handle_message(event)
        self._log_chat_trace(
            {
                "request_id": request_id,
                "stage": "llm_pipeline_finished",
                "status": result.get("status", "unknown"),
                "finish_reason": result.get("finish_reason"),
            }
        )
        return result

    def _update_history_record(self, request_id: str, **updates: str) -> None:
        for row in self._history:
            if row.get("request_id") == request_id:
                row.update(updates)
                return

    def _run_async_send(self, request_id: str, event: dict[str, Any]) -> None:
        started_at = datetime.now()
        with self._lock:
            if request_id in self._jobs:
                self._jobs[request_id].update(
                    {
                        "status": "running",
                        "started_at": started_at.isoformat(),
                    }
                )
            self._update_history_record(request_id, status="running")
        self._log_chat_trace({"request_id": request_id, "stage": "worker_started"})

        try:
            result = self._process_event(request_id=request_id, event=event)
            finished_at = datetime.now()
            duration_ms = int((finished_at - started_at).total_seconds() * 1000)
            with self._lock:
                self._jobs[request_id].update(
                    {
                        "status": str(result.get("status", "unknown")),
                        "result": result,
                        "finished_at": finished_at.isoformat(),
                        "duration_ms": duration_ms,
                    }
                )
                self._update_history_record(
                    request_id,
                    noty=str(result.get("text", "(ответ не сгенерирован)")),
                    status=str(result.get("status", "unknown")),
                    duration_ms=str(duration_ms),
                )
            self._log_chat_trace(
                {
                    "request_id": request_id,
                    "stage": "worker_finished",
                    "status": result.get("status", "unknown"),
                    "duration_ms": duration_ms,
                }
            )
        except Exception as exc:  # noqa: BLE001
            finished_at = datetime.now()
            duration_ms = int((finished_at - started_at).total_seconds() * 1000)
            with self._lock:
                self._jobs[request_id].update(
                    {
                        "status": "error",
                        "error": str(exc),
                        "finished_at": finished_at.isoformat(),
                        "duration_ms": duration_ms,
                    }
                )
                self._update_history_record(
                    request_id,
                    noty=f"(ошибка: {exc})",
                    status="error",
                    duration_ms=str(duration_ms),
                )
            self._log_chat_trace(
                {
                    "request_id": request_id,
                    "stage": "worker_failed",
                    "error": str(exc),
                    "duration_ms": duration_ms,
                }
            )

    def enqueue_send(self, user_text: str, chat_id: int, user_id: int, username: str) -> str:
        request_id = uuid.uuid4().hex
        event = {
            "platform": "web_panel",
            "chat_id": chat_id,
            "user_id": user_id,
            "text": user_text,
            "is_private": True,
            "username": username,
            "chat_name": f"web_panel_chat_{chat_id}",
            "force_respond": True,
        }
        accepted_at = datetime.now()
        with self._lock:
            self._jobs[request_id] = {
                "request_id": request_id,
                "status": "pending",
                "accepted_at": accepted_at.isoformat(),
                "event": {
                    "chat_id": chat_id,
                    "user_id": user_id,
                    "username": username,
                },
            }
            self._history.append(
                {
                    "request_id": request_id,
                    "timestamp": accepted_at.strftime("%H:%M:%S"),
                    "user": user_text,
                    "noty": "(в обработке)",
                    "status": "pending",
                    "duration_ms": "",
                }
            )
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit :]
        self._log_chat_trace(
            {
                "request_id": request_id,
                "stage": "accepted",
                "chat_id": chat_id,
                "user_id": user_id,
            }
        )

        worker = threading.Thread(
            target=self._run_async_send,
            args=(request_id, event),
            daemon=True,
            name=f"noty-web-panel-{request_id[:8]}",
        )
        worker.start()
        return request_id

    def _build_bot(self) -> Any:
        from main import build_bot, load_yaml

        config = load_yaml(str(PATHS.bot_config_path))
        return build_bot(config)

    def send(self, user_text: str, chat_id: int, user_id: int, username: str) -> dict[str, Any]:
        request_id = uuid.uuid4().hex
        event = {
            "platform": "web_panel",
            "chat_id": chat_id,
            "user_id": user_id,
            "text": user_text,
            "is_private": True,
            "username": username,
            "chat_name": f"web_panel_chat_{chat_id}",
            "force_respond": True,
        }
        started_at = datetime.now()
        result = self._process_event(request_id=request_id, event=event)
        duration_ms = int((datetime.now() - started_at).total_seconds() * 1000)
        with self._lock:
            self._history.append(
                {
                    "request_id": request_id,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "user": user_text,
                    "noty": str(result.get("text", "(ответ не сгенерирован)")),
                    "status": str(result.get("status", "unknown")),
                    "duration_ms": str(duration_ms),
                }
            )
            if len(self._history) > self._history_limit:
                self._history = self._history[-self._history_limit :]
        return result

    def status(self, request_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(request_id)
            return dict(job) if job else None

    def health_snapshot(self) -> dict[str, Any]:
        with self._lock:
            jobs = list(self._jobs.values())
        statuses: dict[str, int] = {"pending": 0, "running": 0, "responded": 0, "ignored": 0, "error": 0}
        completed_durations: list[int] = []
        last_error: str | None = None
        for job in jobs:
            status_name = str(job.get("status", "unknown"))
            statuses[status_name] = statuses.get(status_name, 0) + 1
            if isinstance(job.get("duration_ms"), int):
                completed_durations.append(job["duration_ms"])
            if status_name == "error":
                last_error = str(job.get("error", "unknown"))
        avg_duration = int(sum(completed_durations) / len(completed_durations)) if completed_durations else 0
        return {
            "jobs_total": len(jobs),
            "statuses": statuses,
            "avg_duration_ms": avg_duration,
            "last_error": last_error,
        }

    def history(self) -> list[dict[str, str]]:
        with self._lock:
            return list(self._history)


CHAT_SIMULATOR = LocalPanelChatSimulator()


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
    history = CHAT_SIMULATOR.history()

    return {
        "vk_token": transport.get("vk_token", ""),
        "vk_group_id": transport.get("vk_group_id", ""),
        "llm_backend": llm_cfg.get("backend", "openai"),
        "openrouter_api_key": env_data.get("OPENROUTER_API_KEY", ""),
        "hf_token": env_data.get("HF_TOKEN", ""),
        "hf_hub_disable_symlinks_warning": env_data.get("HF_HUB_DISABLE_SYMLINKS_WARNING", "1"),
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
        "full_logs": _collect_full_logs(),
        "chat_history": history,
        "chat_health": CHAT_SIMULATOR.health_snapshot(),
    }


def _render_chat_rows_html(history: list[dict[str, str]]) -> str:
    return "".join(
        (
            "<article class='chat-row'>"
            f"<div class='chat-meta'><b>{html.escape(row['timestamp'])}</b>"
            f"<span>status: {html.escape(row['status'])}</span>"
            f"<span>req: {html.escape(row.get('request_id', '-'))}</span>"
            f"<span>{html.escape(row.get('duration_ms', '-'))} ms</span></div>"
            f"<div><b>Ты:</b> {html.escape(row['user'])}</div>"
            f"<div><b>Ноти:</b> {html.escape(row['noty'])}</div>"
            "</article>"
        )
        for row in history
    )


def _read_tail(path: Path, max_lines: int = 400) -> str:
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    return "\n".join(lines[-max_lines:])


def _collect_jsonl_tail(log_dir: Path, max_lines: int = 250) -> str:
    if not log_dir.exists():
        return ""
    files = sorted(log_dir.glob("*.jsonl"))
    if not files:
        return ""
    latest = files[-1]
    return _read_tail(latest, max_lines=max_lines)


def _collect_full_logs() -> str:
    sections: list[str] = []
    runtime = _read_tail(RUNTIME_LOG_PATH, max_lines=500)
    interactions = _collect_jsonl_tail(INTERACTIONS_LOG_DIR)
    thoughts = _collect_jsonl_tail(THOUGHTS_LOG_DIR)
    actions = _collect_jsonl_tail(ACTIONS_LOG_DIR)
    chat_trace = _read_tail(CHAT_TRACE_LOG_PATH, max_lines=250)

    if runtime:
        sections.append(f"=== Runtime log (main.py stdout/stderr) ===\n{runtime}")
    if interactions:
        sections.append(f"=== Interactions log ===\n{interactions}")
    if thoughts:
        sections.append(f"=== Thoughts log ===\n{thoughts}")
    if actions:
        sections.append(f"=== Actions log ===\n{actions}")
    if chat_trace:
        sections.append(f"=== Web panel chat trace ===\n{chat_trace}")

    return "\n\n".join(sections) if sections else "Логи пока пустые."


def save_runtime_settings(form_data: dict[str, str]) -> None:
    env_data = _read_env(PATHS.env_path)
    env_data["OPENROUTER_API_KEY"] = form_data.get("openrouter_api_key", "").strip()
    env_data["HF_TOKEN"] = form_data.get("hf_token", "").strip()
    env_data["HF_HUB_DISABLE_SYMLINKS_WARNING"] = form_data.get("hf_hub_disable_symlinks_warning", "1").strip() or "1"
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
    running = "online" if vm["service_status"]["running"] else "offline"

    checked_true = "checked" if vm["mem0_enabled"] == "true" else ""
    checked_false = "checked" if vm["mem0_enabled"] != "true" else ""

    safe = {key: html.escape(str(value), quote=True) for key, value in vm.items()}
    chat_rows = _render_chat_rows_html(vm["chat_history"])

    return f"""
    <html>
    <head>
      <meta charset='utf-8'>
      <title>Noty Panel</title>
      <style>
        :root {{ color-scheme: dark; }}
        body {{ font-family: Inter, system-ui, sans-serif; margin: 0; background: #0a0f1f; color: #e8ecff; }}
        .wrap {{ max-width: 1180px; margin: 0 auto; padding: 18px; }}
        .card {{ background: linear-gradient(145deg, #111939, #0d142c); border: 1px solid #22315f; border-radius: 14px; padding: 16px; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }}
        .badge {{ padding: 5px 10px; border-radius: 999px; font-size: 12px; background: #1f2f63; }}
        .badge.offline {{ background: #5b2434; }}
        .actions form {{ display: inline-block; margin-right: 8px; }}
        button {{ cursor: pointer; border: 0; border-radius: 10px; padding: 8px 12px; background: #385cff; color: #fff; font-weight: 600; }}
        .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }}
        .chat-stream {{ max-height: 440px; overflow: auto; }}
        .chat-row {{ border: 1px solid #25386d; border-radius: 10px; padding: 10px; margin-bottom: 10px; background: #121c3b; }}
        .chat-meta {{ display: flex; gap: 10px; margin-bottom: 8px; font-size: 12px; color: #9db0ed; flex-wrap: wrap; }}
        pre {{ white-space: pre-wrap; background: #090d1b; color: #dce4ff; padding: 12px; border-radius: 10px; max-height: 460px; overflow: auto; border: 1px solid #22315f; }}
        input, textarea {{ width: 100%; border-radius: 8px; border: 1px solid #304174; background: #0f1631; color: #f1f4ff; padding: 8px; }}
        details {{ margin-top: 14px; }}
      </style>
    </head>
    <body>
    <div class='wrap'>
      <section class='card'>
        <div class='header'>
          <h1 style='margin:0'>Noty live-панель</h1>
          <span id='serviceBadge' class='badge {running}'>{running}</span>
        </div>

        <div class='actions'>
          <form method='post' action='/service/start' style='display:inline-block'><button>Запустить</button></form>
          <form method='post' action='/service/stop' style='display:inline-block'><button>Остановить</button></form>
          <form method='post' action='/service/reload' style='display:inline-block'><button>Перезагрузить</button></form>
        </div>

        <div class='grid'>
          <section class='card'>
            <h2 style='margin-top:0'>Быстрый чат / ответы</h2>
            <p id='chatHealth'><b>Chat health:</b> jobs={vm['chat_health']['jobs_total']} | avg_duration_ms={vm['chat_health']['avg_duration_ms']} | statuses={html.escape(str(vm['chat_health']['statuses']))}</p>
      <form method='post' action='/chat/send'>
        <label>Chat ID<br><input name='chat_id' style='width:100%' value='9001'></label><br><br>
        <label>User ID<br><input name='user_id' style='width:100%' value='1001'></label><br><br>
        <label>Username<br><input name='username' style='width:100%' value='web_user'></label><br><br>
        <label>Сообщение Ноти<br><textarea name='message_text' rows='4' style='width:100%'></textarea></label><br><br>
        <button type='submit'>Отправить</button>
      </form>
            <div id='chatRows' class='chat-stream' style='margin-top:12px'>{chat_rows or '<i>Диалог пока пуст.</i>'}</div>
          </section>
          <section class='card'>
            <h2 style='margin-top:0'>Логи (автообновление)</h2>
            <pre id='liveLogs'>{safe['full_logs']}</pre>
          </section>
        </div>

        <details>
          <summary>Расширенные настройки</summary>
          <form method='post' action='/save'>
            <h3>Параметры подключения</h3>
            <label>VK token<br><input name='vk_token' value='{safe['vk_token']}'></label><br><br>
            <label>VK group id<br><input name='vk_group_id' value='{safe['vk_group_id']}'></label><br><br>
            <label>LLM backend<br><input name='llm_backend' value='{safe['llm_backend']}'></label><br><br>
            <label>OpenRouter API key<br><input name='openrouter_api_key' value='{safe['openrouter_api_key']}'></label><br><br>
            <label>HF token<br><input name='hf_token' value='{safe['hf_token']}'></label><br><br>
            <label>HF disable symlink warning<br><input name='hf_hub_disable_symlinks_warning' value='{safe['hf_hub_disable_symlinks_warning']}'></label><br><br>
            <label>SQLite path<br><input name='sqlite_path' value='{safe['sqlite_path']}'></label><br><br>
            <label><input type='radio' name='mem0_enabled' value='true' {checked_true}> Mem0 включён</label>
            <label><input type='radio' name='mem0_enabled' value='false' {checked_false}> Mem0 выключен</label><br><br>
            <label>Mem0 API key<br><input name='mem0_api_key' value='{safe['mem0_api_key']}'></label><br><br>
            <label>Qdrant URL<br><input name='qdrant_url' value='{safe['qdrant_url']}'></label><br><br>
            <label>Qdrant API key<br><input name='qdrant_api_key' value='{safe['qdrant_api_key']}'></label><br><br>
            <label>Новый пароль панели<br><input name='local_panel_password' type='password'></label><br><br>
            <label>Prompt config JSON<br><textarea name='prompt_config_json' rows='16'>{safe['prompt_config_json']}</textarea></label><br><br>
            <button type='submit'>Сохранить настройки</button>
          </form>
        </details>
      </section>
    </div>
    <script>
      function escapeHtml(text) {{
        return text
          .replaceAll('&', '&amp;')
          .replaceAll('<', '&lt;')
          .replaceAll('>', '&gt;')
          .replaceAll('"', '&quot;')
          .replaceAll("'", '&#039;');
      }}

      function renderChatRows(rows) {{
        if (!rows.length) return '<i>Диалог пока пуст.</i>';
        return rows.map((row) => {{
          const ts = escapeHtml(String(row.timestamp || '-'));
          const status = escapeHtml(String(row.status || '-'));
          const req = escapeHtml(String(row.request_id || '-'));
          const ms = escapeHtml(String(row.duration_ms || '-'));
          const user = escapeHtml(String(row.user || ''));
          const noty = escapeHtml(String(row.noty || ''));
          return `<article class="chat-row"><div class="chat-meta"><b>${{ts}}</b><span>status: ${{status}}</span><span>req: ${{req}}</span><span>${{ms}} ms</span></div><div><b>Ты:</b> ${{user}}</div><div><b>Ноти:</b> ${{noty}}</div></article>`;
        }}).join('');
      }}

      async function refreshLive() {{
        try {{
          const response = await fetch('/panel/live', {{ cache: 'no-store' }});
          if (!response.ok) return;
          const data = await response.json();
          const badge = document.getElementById('serviceBadge');
          const state = data.service_status.running ? 'online' : 'offline';
          badge.className = `badge ${{state}}`;
          badge.textContent = state;

          document.getElementById('chatHealth').innerHTML = `<b>Chat health:</b> jobs=${{data.chat_health.jobs_total}} | avg_duration_ms=${{data.chat_health.avg_duration_ms}} | statuses=${{escapeHtml(JSON.stringify(data.chat_health.statuses))}}`;
          document.getElementById('chatRows').innerHTML = renderChatRows(data.chat_history || []);
          document.getElementById('liveLogs').textContent = data.full_logs || 'Логи пока пустые.';
        }} catch (_e) {{}}
      }}

      setInterval(refreshLive, 1500);
    </script>
    </body>
    </html>
    """


@app.get("/panel/live")
def panel_live(_: str = Depends(_verify_auth)) -> JSONResponse:
    return JSONResponse(
        {
            "service_status": PROCESS_MANAGER.status(),
            "chat_history": CHAT_SIMULATOR.history(),
            "chat_health": CHAT_SIMULATOR.health_snapshot(),
            "full_logs": _collect_full_logs(),
        }
    )


@app.post("/save")
def save(
    request: Request,
    vk_token: str = Form(""),
    vk_group_id: str = Form("0"),
    llm_backend: str = Form("openai"),
    openrouter_api_key: str = Form(""),
    hf_token: str = Form(""),
    hf_hub_disable_symlinks_warning: str = Form("1"),
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
        "hf_token": hf_token,
        "hf_hub_disable_symlinks_warning": hf_hub_disable_symlinks_warning,
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


@app.post("/chat/send")
def chat_send(
    request: Request,
    message_text: str = Form(""),
    chat_id: str = Form("9001"),
    user_id: str = Form("1001"),
    username: str = Form("web_user"),
    _: str = Depends(_verify_auth),
) -> RedirectResponse:
    if message_text.strip():
        CHAT_SIMULATOR.enqueue_send(
            user_text=message_text.strip(),
            chat_id=int(chat_id or 9001),
            user_id=int(user_id or 1001),
            username=username.strip() or "web_user",
        )
    return RedirectResponse(url=str(request.url_for("index")), status_code=303)


@app.get("/chat/health")
def chat_health(_: str = Depends(_verify_auth)) -> JSONResponse:
    return JSONResponse(CHAT_SIMULATOR.health_snapshot())


@app.get("/chat/status/{request_id}")
def chat_status(request_id: str, _: str = Depends(_verify_auth)) -> JSONResponse:
    status_payload = CHAT_SIMULATOR.status(request_id)
    if status_payload is None:
        return JSONResponse({"error": "request_id_not_found", "request_id": request_id}, status_code=404)
    return JSONResponse(status_payload)
