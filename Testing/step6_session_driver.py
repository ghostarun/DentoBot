"""Persistent headed Step 6 session: checkpoint once, then run commands and hot-reload.

Operator request 2026-10-02: avoid restarting Slicer/ROS/MoveIt from zero for every
Python change. With ``DENTOBOT_HEADED_SESSION=1`` the headed runner stops after
ROS connect and scene acknowledgement and serves a private command inbox:

    <run>/session/inbox/NNN-name.py   command script (executed in Slicer's main thread)
    <run>/session/outbox/NNN-name.json result: status, result, traceback, duration
    <run>/session/running/            the script currently executing
    <run>/session/done/               consumed scripts
    <run>/session/heartbeat           touched every few seconds
    <run>/session/ready.json          written when the loop is serving

A script sees the runner's namespace (widget, panel, facade, logic, parameter_node,
report helpers) plus ``reload_changed()`` and ``mod(name)``, and sets ``result``.
A script named ``*stop*.py`` ends the session. Commands come only from files the
coordinator writes into the run's private (0700) directory. Simulation only.

Hot reload covers pure/logic modules, the facade, panel, widget mixins and probes.
It never reloads ROS-stateful modules (``DENTOROS2Bridge`` keeps live subscriptions
in module globals); a change there, a C++ change, or a UI layout change needs a
fresh session.
"""

from __future__ import annotations

import importlib
import json
import sys
import time
import traceback
from pathlib import Path

NEVER_RELOAD = frozenset({"DENTOROS2Bridge", "step6_session_driver"})
RELOAD_PREFIXES = ("dentobot_workflow", "DENTO", "step6_")
IDLE_LIMIT_SEC = 45 * 60


def _jsonable(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return str(value)


def _module_file(module) -> Path | None:
    path = getattr(module, "__file__", None)
    return Path(path) if path and str(path).endswith(".py") else None


def reloadable_modules(modules=None) -> dict:
    modules = sys.modules if modules is None else modules
    selected = {}
    for name, module in list(modules.items()):
        if module is None or not name.startswith(RELOAD_PREFIXES):
            continue
        if name.split(".")[0] in NEVER_RELOAD or name in NEVER_RELOAD:
            continue
        if _module_file(module) is None:
            continue
        selected[name] = module
    return selected


def _dependencies(module, names) -> set:
    deps = set()
    for value in vars(module).values():
        owner = getattr(value, "__name__", None) if isinstance(value, type(sys)) else getattr(
            value, "__module__", None
        )
        if owner in names and owner != module.__name__:
            deps.add(owner)
    return deps


def reload_order(changed: set, modules: dict) -> list:
    """Changed modules plus their dependents, dependencies first."""
    names = set(modules)
    deps = {name: _dependencies(module, names) for name, module in modules.items()}
    affected = set(changed)
    grew = True
    while grew:
        grew = False
        for name, needed in deps.items():
            package = str(getattr(modules[name], "__file__", "")).endswith("__init__.py")
            if name not in affected and not package and needed & affected:
                affected.add(name)
                grew = True
    order, visiting, done = [], set(), set()

    def visit(name):
        if name in done or name in visiting:
            return
        visiting.add(name)
        for dep in sorted(deps.get(name, ())):
            if dep in affected:
                visit(dep)
        visiting.discard(name)
        done.add(name)
        order.append(name)

    for name in sorted(affected):
        visit(name)
    return order


class HotReloader:
    """Reload changed modules and move live objects onto the new classes."""

    def __init__(self, live_objects):
        self.live_objects = live_objects  # callable -> list of live instances
        self.mtimes = self._snapshot()
        self.blocked_mtimes = self._blocked_snapshot()

    @staticmethod
    def _snapshot() -> dict:
        stamps = {}
        for name, module in reloadable_modules().items():
            try:
                stamps[name] = _module_file(module).stat().st_mtime_ns
            except OSError:
                pass
        return stamps

    @staticmethod
    def _blocked_snapshot() -> dict:
        stamps = {}
        for name in NEVER_RELOAD:
            path = _module_file(sys.modules.get(name)) if sys.modules.get(name) else None
            if path is not None and path.exists():
                stamps[name] = path.stat().st_mtime_ns
        return stamps

    def note_new_modules(self) -> None:
        """Baseline modules first imported during a command (r16: lazily imported
        modules were otherwise reported as changed on the next reload)."""
        for name, stamp in self._snapshot().items():
            self.mtimes.setdefault(name, stamp)

    def reload_changed(self) -> dict:
        modules = reloadable_modules()
        current = self._snapshot()
        changed = {name for name, stamp in current.items() if self.mtimes.get(name) != stamp}
        order = reload_order(changed, modules)
        reloaded, errors = [], {}
        for name in order:
            try:
                importlib.reload(sys.modules[name])
                reloaded.append(name)
            except Exception:  # keep the session alive; report the failure
                errors[name] = traceback.format_exc(limit=5)
        swapped = []
        for obj in self.live_objects():
            if obj is None:
                continue
            cls = type(obj)
            if cls.__module__ not in reloaded:
                continue
            new_cls = getattr(sys.modules[cls.__module__], cls.__name__, None)
            if isinstance(new_cls, type) and new_cls is not cls:
                obj.__class__ = new_cls
                swapped.append(f"{cls.__module__}.{cls.__name__}")
        self.mtimes = self._snapshot()
        restart_required = sorted(
            name for name, stamp in self._blocked_snapshot().items()
            if self.blocked_mtimes.get(name) != stamp
        )
        return {"changed": sorted(changed), "reloaded": reloaded, "errors": errors,
                "swapped": swapped, "restart_required": restart_required}


def rebind_callbacks(callbacks: dict, owner) -> int:
    """Point bound-method callbacks at the owner's current (reloaded) class."""
    count = 0
    for key, value in list(callbacks.items()):
        func = getattr(value, "__func__", None)
        if func is not None and getattr(value, "__self__", None) is owner:
            callbacks[key] = getattr(owner, func.__name__)
            count += 1
    return count


def run_session(namespace: dict, session_dir: Path, process_events, *, idle_limit_sec=IDLE_LIMIT_SEC,
                clock=time.monotonic, poll_sec=0.25) -> dict:
    inbox, running, outbox, done = (
        session_dir / part for part in ("inbox", "running", "outbox", "done")
    )
    for path in (inbox, running, outbox, done):
        path.mkdir(parents=True, exist_ok=True)
    heartbeat = session_dir / "heartbeat"
    reloader = HotReloader(namespace.get("live_objects") or (lambda: ()))
    namespace = dict(namespace)
    after_reload = namespace.get("after_reload")

    def reload_changed():
        report = reloader.reload_changed()
        if callable(after_reload):
            report["after_reload"] = _jsonable(after_reload())
        return report

    namespace["reload_changed"] = reload_changed
    namespace["rebind_callbacks"] = rebind_callbacks
    namespace["mod"] = lambda name: sys.modules[name]
    (session_dir / "ready.json").write_text(json.dumps({"ready": True, "pid": __import__("os").getpid()}))
    print("DENTOBOT_SESSION_READY", flush=True)
    last_command = last_beat = last_print = clock()
    executed = []
    while True:
        now = clock()
        if now - last_beat >= 2.0:
            heartbeat.touch()
            last_beat = now
        if now - last_print >= 60.0:
            print("DENTOBOT_SESSION_HEARTBEAT", flush=True)
            last_print = now
        if now - last_command > idle_limit_sec:
            return {"reason": "idle_limit", "executed": executed}
        scripts = sorted(inbox.glob("*.py"))
        if not scripts:
            process_events(poll_sec)
            continue
        script = scripts[0].rename(running / scripts[0].name)
        name = script.stem
        started = clock()
        record = {"command": name, "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        scope = dict(namespace)
        scope["result"] = None
        try:
            code = compile(script.read_text(), str(script), "exec")
            print(f"DENTOBOT_SESSION_COMMAND_START {name}", flush=True)
            exec(code, scope)  # noqa: S102 - coordinator-written file in the private run dir
            record.update(status="ok", result=_jsonable(scope.get("result")))
        except SystemExit:
            raise
        except BaseException:
            record.update(status="error", result=_jsonable(scope.get("result")),
                          traceback=traceback.format_exc(limit=12))
        record["duration_sec"] = round(clock() - started, 3)
        reloader.note_new_modules()
        # Atomic: results can be ~10 MB (r22 cycles) and the host sender polls
        # the outbox; it must never read a half-written file.
        staging = outbox / f".{name}.json.tmp"
        staging.write_text(json.dumps(record, indent=2))
        staging.rename(outbox / f"{name}.json")
        script.rename(done / script.name)
        print(f"DENTOBOT_SESSION_COMMAND_END {name} {record['status']} {record['duration_sec']}s", flush=True)
        executed.append({"command": name, "status": record["status"], "duration_sec": record["duration_sec"]})
        last_command = clock()
        if "stop" in name:
            return {"reason": "stop_command", "executed": executed}
