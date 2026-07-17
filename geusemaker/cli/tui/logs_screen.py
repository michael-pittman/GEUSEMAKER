"""Live log streaming screen: named log-target picker + SSM stream pane.

Implements streams 2–3 of the log streaming contract (spec:
tui-brutalist-rollout §8.4): server-side instance log files are tailed via
``SSMService.tail_file`` and docker container logs are followed via
``SSMService.follow_container_logs``. The known log catalog (``LOG_TARGETS``)
is the UI source of truth — the left pane is a picker, never a free-text path
prompt.

Streaming is dependency-injected (``LogStreamFactory``) so tests never touch
AWS; the default factory resolves the target through ``LOG_TARGETS`` and
delegates to the real SSM primitives with function-local imports (the TUI
must not import ``geusemaker.services`` at module import time).

Worker rules honored here: the blocking stream generator runs in a
``@work(thread=True, exclusive=True, group="log-stream")`` worker; UI
mutations only via ``call_from_thread`` guarded by a ``_ui_closed`` event;
switching targets cancels the active worker (stop event + generator
``close()``) — a stream never ends silently: [ENDED], [ERROR], or
[DETACHED] is always rendered.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import ClassVar

from rich.markup import escape
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Label, ListItem, ListView, RichLog, Static

from geusemaker.cli.tui.theme import GM_FAULT, GM_MUTED, GM_SIGNAL, GM_VARIABLES_TCSS, GM_WARN
from geusemaker.infra.state import StateError, StateManager

#: Dependency-injection seam: ``(instance_id, target_key) -> lines``. The
#: returned iterator may block between lines; it is always consumed inside a
#: thread worker. Real impl: `LogsScreen._default_stream_factory` (SSM).
LogStreamFactory = Callable[[str, str], Iterator[str]]

STREAM_LOG_MAX_LINES = 2000

#: Prefix for picker ListItem ids: ``target-<target_key>``.
TARGET_ITEM_PREFIX = "target-"

#: Named log-target catalog (ordered; §8.4.2 "a picker, not a free-text path
#: prompt"). ``("file", path)`` targets stream via SSMService.tail_file;
#: ``("container", service)`` targets via SSMService.follow_container_logs.
LOG_TARGETS: dict[str, tuple[str, str]] = {
    "userdata": ("file", "/var/log/geusemaker-userdata.log"),
    "model-preload": ("file", "/var/log/geusemaker/model-preload.log"),
    "efs-mount": ("file", "/var/log/amazon/efs/mount.log"),
    "n8n": ("container", "n8n"),
    "ollama": ("container", "ollama"),
    "qdrant": ("container", "qdrant"),
    "crawl4ai": ("container", "crawl4ai"),
    "postgres": ("container", "postgres"),
}

_GROUP_LABELS = {"file": "INSTANCE", "container": "CONTAINERS"}

# Uppercase bracketed badges are literal text under Rich markup (tags must
# start lowercase/#/@//), so [WAIT]/[ENDED]/... render verbatim.
_OK_MARK = f"[bold {GM_SIGNAL}][OK][/bold {GM_SIGNAL}]"
_WAIT_MARK = f"[bold {GM_WARN}][WAIT][/bold {GM_WARN}]"
_ERROR_MARK = f"[bold {GM_FAULT}][ERROR][/bold {GM_FAULT}]"
_ENDED_MARK = f"[bold {GM_MUTED}][ENDED][/bold {GM_MUTED}]"
_DETACHED_MARK = f"[bold {GM_WARN}][DETACHED][/bold {GM_WARN}]"


class LogsScreen(Screen[None]):
    """Log-target picker (instance files + containers) + live stream pane."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss_screen", "BACK"),
        Binding("s", "stop_stream", "STOP STREAM"),
    ]

    # $gm-* tokens come from theme.GM_VARIABLES_TCSS (DEFAULT_CSS cannot see
    # app-stylesheet variables in Textual 8.2.8).
    DEFAULT_CSS = (
        GM_VARIABLES_TCSS
        + """
    LogsScreen {
        background: $gm-surface;
        color: $gm-ink;
    }
    #logs-root {
        padding: 1 2;
    }
    #logs-title {
        height: 3;
        padding: 0 1;
        border: heavy $gm-signal;
        color: $gm-signal;
        text-style: bold;
    }
    #logs-workspace {
        height: 1fr;
        margin-top: 1;
    }
    #logs-targets {
        width: 30;
        background: $gm-panel;
        border: heavy $gm-rule;
    }
    #logs-targets-title {
        height: 3;
        padding: 0 1;
        border: heavy $gm-signal;
        color: $gm-signal;
        text-style: bold;
    }
    #logs-target-list {
        background: $gm-panel;
        border: none;
    }
    #logs-target-list ListItem {
        height: auto;
        padding: 0 1;
        color: $gm-ink;
    }
    #logs-target-list ListItem.logs-group {
        color: $gm-muted;
        text-style: bold;
    }
    #logs-main {
        width: 1fr;
        margin-left: 1;
    }
    #logs-status {
        height: 3;
        padding: 0 1;
        border: heavy $gm-rule;
        color: $gm-ink;
    }
    #logs-stream {
        height: 1fr;
        min-height: 5;
        margin-top: 1;
        padding: 0 1;
        border: heavy $gm-rule;
        background: $gm-panel;
        color: $gm-ink;
    }
    """
    )

    def __init__(
        self,
        *,
        stack_name: str,
        state_dir: Path | None = None,
        stream_factory: LogStreamFactory | None = None,
    ) -> None:
        super().__init__()
        self.stack_name = stack_name
        self.state_dir = state_dir
        self._stream_factory: LogStreamFactory = stream_factory or self._default_stream_factory
        self._instance_id: str | None = None
        self._region: str | None = None
        #: Currently attached target key (None when no stream is active).
        self._active_target: str | None = None
        #: Live stream objects keyed by attach token, published by workers so
        #: the UI thread can close() them to unblock an iterator stuck
        #: between yields. Workers pop their own entry on exit.
        self._streams: dict[int, Iterator[str]] = {}
        #: Monotonic attach counter; stale worker callbacks compare against it.
        self._stream_seq = 0
        self._live_token = -1
        # Thread-shared guards (never named _closed/_running: those collide
        # with Textual MessagePump internals). _stream_stop is replaced per
        # attach so an old worker can never observe a new stream's event.
        self._stream_stop = threading.Event()
        self._ui_closed = threading.Event()

    # ------------------------------------------------------------------ UI --

    def compose(self) -> ComposeResult:
        with Vertical(id="logs-root"):
            yield Static(f"LOGS · STACK {self.stack_name.upper()}", id="logs-title")
            with Horizontal(id="logs-workspace"):
                with Vertical(id="logs-targets"):
                    yield Static("TARGETS", id="logs-targets-title")
                    yield ListView(*self._picker_items(), id="logs-target-list", disabled=True)
                with Vertical(id="logs-main"):
                    yield Static(
                        f"{_WAIT_MARK} LOADING STATE FOR '{self.stack_name.upper()}'",
                        id="logs-status",
                    )
                    yield RichLog(
                        id="logs-stream",
                        auto_scroll=True,
                        max_lines=STREAM_LOG_MAX_LINES,
                        markup=True,
                        highlight=False,
                    )

    @staticmethod
    def _picker_items() -> list[ListItem]:
        """LOG_TARGETS as list items, visually grouped INSTANCE / CONTAINERS."""
        items: list[ListItem] = []
        current_kind: str | None = None
        for key, (kind, _target) in LOG_TARGETS.items():
            if kind != current_kind:
                current_kind = kind
                group = _GROUP_LABELS[kind]
                items.append(
                    ListItem(
                        Label(f"— {group} —", markup=False),
                        id=f"group-{group.lower()}",
                        classes="logs-group",
                        disabled=True,
                    )
                )
            items.append(ListItem(Label(key.upper(), markup=False), id=f"{TARGET_ITEM_PREFIX}{key}"))
        return items

    def on_mount(self) -> None:
        self.query_one("#logs-stream", RichLog).write(
            f"{_WAIT_MARK} LOADING STATE FOR '{self.stack_name.upper()}'",
        )
        self._load_state()

    def on_unmount(self) -> None:
        self._ui_closed.set()
        self._close_active_stream()

    # -------------------------------------------------------------- actions --

    def action_dismiss_screen(self) -> None:
        self._ui_closed.set()
        self._close_active_stream()
        self.dismiss(None)

    def action_stop_stream(self) -> None:
        """Explicit detach ('s'): stop the stream, keep the pane readable."""
        if self._active_target is None:
            return
        label = self._active_target.upper()
        self._active_target = None
        self._close_active_stream()
        self._stream_seq += 1  # invalidate late lines from the old worker
        self.query_one("#logs-stream", RichLog).write(f"{_DETACHED_MARK} STREAM DETACHED · {label}")
        self.query_one("#logs-status", Static).update(f"{_DETACHED_MARK} {label} · SELECT A TARGET TO REATTACH")

    # -------------------------------------------------------- state loading --

    @work(exclusive=True, group="state-load")
    async def _load_state(self) -> None:
        """Load deployment state from disk (StateManager); ZERO AWS calls."""
        try:
            manager = await asyncio.to_thread(StateManager, self.state_dir)
            state = await manager.load_deployment(self.stack_name)
        except StateError as exc:
            self._show_fatal(f"STATE LOAD FAILED · {exc}")
            return
        if state is None:
            self._show_fatal(f"NO DEPLOYMENT STATE FOUND FOR '{self.stack_name}'")
            return
        if not state.instance_id:
            self._show_fatal(f"NO INSTANCE ID IN STATE FOR '{self.stack_name}' · CANNOT ATTACH SSM LOG STREAMS")
            return
        self._instance_id = state.instance_id
        self._region = state.config.region
        picker = self.query_one("#logs-target-list", ListView)
        picker.disabled = False
        picker.focus()
        self.query_one("#logs-status", Static).update(
            f"{_OK_MARK} INSTANCE {state.instance_id} · SELECT A TARGET",
        )
        self.query_one("#logs-stream", RichLog).write(
            f"{_OK_MARK} INSTANCE {state.instance_id} · {self._region} · SELECT A LOG TARGET",
        )

    def _show_fatal(self, message: str) -> None:
        """Explicit error state: pane text + disabled picker — never a crash."""
        self.query_one("#logs-status", Static).update(f"{_ERROR_MARK} {message}")
        self.query_one("#logs-stream", RichLog).write(f"{_ERROR_MARK} {message}")
        self.query_one("#logs-target-list", ListView).disabled = True

    # ------------------------------------------------------------ selection --

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "logs-target-list":
            return
        item_id = event.item.id
        if not item_id or not item_id.startswith(TARGET_ITEM_PREFIX):
            return
        target_key = item_id.removeprefix(TARGET_ITEM_PREFIX)
        if target_key in LOG_TARGETS:
            self._attach_target(target_key)

    def _attach_target(self, target_key: str) -> None:
        """Cancel any active stream, clear the pane, start the new worker."""
        if self._instance_id is None:
            return
        self._close_active_stream()
        self._stream_seq += 1
        token = self._stream_seq
        stop = threading.Event()
        self._stream_stop = stop
        self._active_target = target_key
        label = target_key.upper()
        log = self.query_one("#logs-stream", RichLog)
        log.clear()
        log.write(f"{_WAIT_MARK} ATTACHING · {label}")
        self.query_one("#logs-status", Static).update(f"{_WAIT_MARK} ATTACHING · {label}")
        self._run_stream(token, self._instance_id, target_key, stop)

    def _close_active_stream(self) -> None:
        """Stop the active worker cooperatively and close its generator.

        close() from the UI thread unblocks stream objects that support it
        (e.g. fakes blocking on an Event); a real generator currently
        executing in the worker thread raises ValueError — swallowed here,
        the worker closes it itself at the next yield via the stop event.
        """
        self._stream_stop.set()
        for stream in list(self._streams.values()):
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except (RuntimeError, ValueError):
                    pass

    # -------------------------------------------------------- stream worker --

    @work(thread=True, exclusive=True, group="log-stream")
    def _run_stream(self, token: int, instance_id: str, target_key: str, stop: threading.Event) -> None:
        """Iterate the blocking stream; every termination renders explicitly."""
        label = target_key.upper()
        try:
            stream = self._stream_factory(instance_id, target_key)
        except RuntimeError as exc:
            self._call_ui(self._on_stream_error, token, label, str(exc))
            return
        self._streams[token] = stream
        interrupted = stop.is_set() or self._ui_closed.is_set()
        try:
            if not interrupted:
                for line in stream:
                    if stop.is_set() or self._ui_closed.is_set():
                        interrupted = True
                        break
                    self._call_ui(self._append_line, token, line)
        except RuntimeError as exc:
            self._call_ui(self._on_stream_error, token, label, str(exc))
            return
        finally:
            self._streams.pop(token, None)
            close = getattr(stream, "close", None)
            if callable(close):
                try:
                    close()
                except RuntimeError:
                    pass
        if not interrupted:
            self._call_ui(self._on_stream_ended, token, label)

    def _call_ui(self, callback: Callable[..., None], *args: object) -> None:
        if self._ui_closed.is_set():
            return
        try:
            self.app.call_from_thread(callback, *args)
        except RuntimeError:
            # App shut down between the check and the call; nothing to update.
            return

    # --------------------------------------------------------- UI mutations --

    def _append_line(self, token: int, line: str) -> None:
        if token != self._stream_seq or not self.is_mounted:
            return
        if self._live_token != token and self._active_target is not None:
            self._live_token = token
            self.query_one("#logs-status", Static).update(
                f"{_OK_MARK} STREAMING · {self._active_target.upper()}",
            )
        self.query_one("#logs-stream", RichLog).write(escape(line))

    def _on_stream_ended(self, token: int, label: str) -> None:
        """Natural end of stream (completion marker / timeout in SSMService)."""
        if token != self._stream_seq or not self.is_mounted:
            return
        self._active_target = None
        self.query_one("#logs-stream", RichLog).write(f"{_ENDED_MARK} STREAM CLOSED · {label}")
        self.query_one("#logs-status", Static).update(f"{_ENDED_MARK} STREAM CLOSED · {label}")

    def _on_stream_error(self, token: int, label: str, message: str) -> None:
        """Stream failure (e.g. SSM denied / agent not ready) — explicit."""
        if token != self._stream_seq or not self.is_mounted:
            return
        self._active_target = None
        self.query_one("#logs-stream", RichLog).write(f"{_ERROR_MARK} {escape(message)}")
        self.query_one("#logs-status", Static).update(f"{_ERROR_MARK} STREAM FAILED · {label}")

    # ------------------------------------------------------ default factory --

    def _default_stream_factory(self, instance_id: str, target_key: str) -> Iterator[str]:
        """Real SSM-backed stream per the §8.4 contract.

        Function-local imports: the TUI must not import geusemaker.services
        (boto3 import graph) at module import time.
        """
        from geusemaker.infra import AWSClientFactory
        from geusemaker.services.ssm import SSMService

        region = self._region
        if region is None:
            raise RuntimeError("Deployment state not loaded; cannot resolve region for log streaming")
        kind, target = LOG_TARGETS[target_key]
        service = SSMService(AWSClientFactory(), region=region)
        if kind == "file":
            return service.tail_file(instance_id, target, poll_interval=2.0, timeout_seconds=600)
        return service.follow_container_logs(instance_id, target, poll_interval=3.0, timeout_seconds=600)


__all__ = [
    "LOG_TARGETS",
    "STREAM_LOG_MAX_LINES",
    "TARGET_ITEM_PREFIX",
    "LogStreamFactory",
    "LogsScreen",
]
