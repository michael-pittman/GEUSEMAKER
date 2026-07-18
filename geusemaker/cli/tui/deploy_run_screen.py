"""Deployment execution screen: ProgressEvent timeline + live event/log pane.

Runs a (blocking) deployment executor in a thread worker and renders every
``ProgressEvent`` live: a per-stage timeline with the brutalist stage glyphs
plus a streaming event log. When the ``userdata`` stage begins and the EC2
instance id is known (captured from the ``ec2`` stage's ``resource_id``), a
second thread worker attaches the SSM userdata log stream and appends lines to
the same log pane. Terminal states (complete / failed / detached) are always
rendered explicitly — never a silent dead pane (spec: tui-brutalist-rollout
§8.4 stream 1 + worker rules).

Execution is dependency-injected (``DeployExecutor`` / ``UserdataStreamer``)
so tests never touch AWS. The real executor (``default_executor``) constructs
``DeploymentRunner`` exactly like ``InteractiveDeployer`` does; that import is
deliberately function-local because ``geusemaker.cli.interactive.runner``
transitively imports questionary (via ``geusemaker.cli.components`` →
``dialogs``), and the TUI must not import questionary at module import time.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from typing import ClassVar

from rich.markup import escape
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, RichLog, Static

from geusemaker.cli.branding import STAGE_GLYPHS
from geusemaker.cli.progress_events import ProgressCallback, ProgressEvent, Stage
from geusemaker.cli.tui._base import OperationalScreen
from geusemaker.cli.tui.theme import GM_FAULT, GM_INK, GM_MUTED, GM_SIGNAL, GM_VARIABLES_TCSS, GM_WARN
from geusemaker.models import DeploymentConfig, DeploymentState

#: Dependency-injection seam: blocking callable that runs the full deployment,
#: forwarding every ProgressEvent to the callback, returning the final state.
#: Raises RuntimeError (incl. OrchestrationError, a RuntimeError subclass) on
#: failure. Tests inject fakes so no AWS/network is ever touched.
DeployExecutor = Callable[[DeploymentConfig, ProgressCallback], DeploymentState]

#: Dependency-injection seam: instance_id -> blocking iterator of userdata log
#: lines (real impl: SSMService.stream_userdata_logs — 2s poll, stops on the
#: completion marker, error guard file, or 600s timeout).
UserdataStreamer = Callable[[str], Iterator[str]]

EVENT_LOG_MAX_LINES = 2000

#: Stage literal order; alb/cdn rows are filtered per config tier.
STAGE_ORDER: tuple[Stage, ...] = (
    "validate",
    "vpc",
    "sg",
    "efs",
    "iam",
    "ec2",
    "spot",
    "userdata",
    "alb",
    "cdn",
    "health",
    "finalize",
)

STATUS_PENDING = "PENDING"
STATUS_ACTIVE = "ACTIVE"
STATUS_DONE = "DONE"
STATUS_ERROR = "ERROR"

_STATUS_STYLES = {
    STATUS_PENDING: GM_MUTED,
    STATUS_ACTIVE: f"bold {GM_SIGNAL}",
    STATUS_DONE: GM_INK,
    STATUS_ERROR: f"bold {GM_FAULT}",
}

_OK_MARK = f"[bold {GM_SIGNAL}][OK][/bold {GM_SIGNAL}]"
_WAIT_MARK = f"[bold {GM_WARN}][WAIT][/bold {GM_WARN}]"
_WARN_MARK = f"[bold {GM_WARN}][WARN][/bold {GM_WARN}]"
_ERROR_MARK = f"[bold {GM_FAULT}][ERROR][/bold {GM_FAULT}]"


def stages_for_config(config: DeploymentConfig) -> list[Stage]:
    """Timeline rows for this config's tier, in Stage literal order.

    Mirrors DeploymentRunner._select_orchestrator: cdn for Tier 3
    (enable_cdn or tier 'gpu'), alb for Tier 2+ (enable_alb, tier
    'automation', or anything that gets a CDN).
    """
    include_cdn = config.enable_cdn or config.tier == "gpu"
    include_alb = include_cdn or config.enable_alb or config.tier == "automation"
    return [stage for stage in STAGE_ORDER if (stage != "alb" or include_alb) and (stage != "cdn" or include_cdn)]


def default_executor(config: DeploymentConfig, on_progress: ProgressCallback) -> DeploymentState:
    """Run a real deployment via DeploymentRunner (InteractiveDeployer pattern).

    Function-local import: ``geusemaker.cli.interactive.runner`` transitively
    imports questionary (cli.components -> dialogs), which the TUI must not
    pull in at module import time. DeploymentRunner itself never prompts —
    the questionary dependency is an import-graph side effect only.
    """
    from geusemaker.cli.interactive.runner import DeploymentRunner, DeploymentValidationFailed
    from geusemaker.infra import AWSClientFactory, StateManager

    runner = DeploymentRunner(AWSClientFactory(), StateManager())
    try:
        return runner.run(config, on_progress=on_progress)
    except DeploymentValidationFailed as exc:
        # DeploymentValidationFailed subclasses Exception directly; normalize
        # to the executor contract (RuntimeError on failure) so the worker
        # never needs a bare-Exception catch.
        raise RuntimeError(f"Pre-deployment validation failed: {exc.report}") from exc


def default_userdata_streamer(region: str) -> UserdataStreamer:
    """Build the real userdata streamer: SSMService.stream_userdata_logs.

    2s poll; the stream ends on the completion marker, the error guard file,
    or the 600s timeout (semantics owned by SSMService).
    """

    def _stream(instance_id: str) -> Iterator[str]:
        from geusemaker.infra import AWSClientFactory
        from geusemaker.services.ssm import SSMService, UserdataLogStream

        service = SSMService(AWSClientFactory(), region=region)
        # UserdataLogStream preserves the terminal reason (SUCCESS/ERROR/
        # TIMEOUT) through this DI seam so the screen can render it accurately.
        return UserdataLogStream(
            service.stream_userdata_logs(
                instance_id=instance_id,
                poll_interval=2.0,
                timeout_seconds=600,
            )
        )

    return _stream


class DeployRunScreen(OperationalScreen):
    """Live deployment run: stage timeline + event/userdata log pane."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "request_dismiss", "BACK"),
        # A live deploy must only be left via the double-press guard. Screen
        # BINDINGS take priority over App BINDINGS, so bind the app's quit key
        # ("q") to the SAME guarded action here — otherwise a stray "q" bubbles
        # to the app's ("q", "quit") binding and kills the app mid-deploy,
        # skipping the confirmation and the clean stream/UI teardown.
        Binding("q", "request_dismiss", "BACK", show=False),
        # Best-effort ctrl+c intercept. In Textual 8.2.8 ctrl+c does NOT quit
        # (the app binds it to a "press ctrl+q to quit" notification, and the
        # base Screen binds it to copy_text) — priority=True lets this win the
        # priority binding pass so ctrl+c arms the same guard instead.
        Binding("ctrl+c", "request_dismiss", "BACK", show=False, priority=True),
    ]

    # $gm-* tokens come from theme.GM_VARIABLES_TCSS (DEFAULT_CSS cannot see
    # app-stylesheet variables in Textual 8.2.8).
    DEFAULT_CSS = (
        GM_VARIABLES_TCSS
        + """
    DeployRunScreen {
        background: $gm-surface;
        color: $gm-ink;
    }
    #deploy-run-root {
        padding: 1 2;
    }
    #deploy-run-title {
        height: 3;
        padding: 0 1;
        border: heavy $gm-signal;
        color: $gm-signal;
        text-style: bold;
    }
    #deploy-run-status {
        height: 3;
        margin-top: 1;
        padding: 0 1;
        border: heavy $gm-rule;
        color: $gm-ink;
    }
    #deploy-run-timeline {
        height: auto;
        max-height: 16;
        margin-top: 1;
        border: heavy $gm-rule;
        background: $gm-panel;
    }
    #deploy-run-events {
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
        config: DeploymentConfig,
        executor: DeployExecutor | None = None,
        userdata_streamer: UserdataStreamer | None = None,
    ) -> None:
        super().__init__()
        self.config = config
        self._executor: DeployExecutor = executor or default_executor
        self._userdata_streamer: UserdataStreamer = userdata_streamer or default_userdata_streamer(config.region)
        self.stages: list[Stage] = stages_for_config(config)
        #: Public for tests/orchestrator wiring: stage -> PENDING/ACTIVE/DONE/ERROR.
        self.stage_statuses: dict[Stage, str] = dict.fromkeys(self.stages, STATUS_PENDING)
        self._stage_resources: dict[Stage, str] = {}
        self._active_stage: Stage | None = None
        self._instance_id: str | None = None
        self._stream_started = False
        self._deploy_running = True
        # Shared armed state for the double-press dismiss guard: the FIRST
        # escape/q/ctrl+c arms it (warn line), the SECOND detaches. All three
        # keys route through action_request_dismiss, so one press of any of
        # them arms the guard and any second press dismisses.
        self._dismiss_armed = False
        # Thread-shared guards: set on dismissal/unmount (drop late events) and
        # at terminal state (detach the userdata stream generator cleanly).
        self._ui_closed = threading.Event()
        self._stream_stop = threading.Event()

    # ------------------------------------------------------------------ UI --

    def compose(self) -> ComposeResult:
        with Vertical(id="deploy-run-root"):
            yield Static(f"DEPLOY · STACK {self.config.stack_name.upper()}", id="deploy-run-title")
            yield Static(
                f"{_WAIT_MARK} DEPLOY STARTING · STACK {self.config.stack_name.upper()}",
                id="deploy-run-status",
            )
            yield DataTable(id="deploy-run-timeline")
            yield RichLog(
                id="deploy-run-events",
                auto_scroll=True,
                max_lines=EVENT_LOG_MAX_LINES,
                markup=True,
                highlight=False,
            )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#deploy-run-timeline", DataTable)
        table.cursor_type = "none"
        self._col_keys = table.add_columns("MARK", "STAGE", "STATUS", "RESOURCE")
        for stage in self.stages:
            glyph = STAGE_GLYPHS[stage].splitlines()[0]
            table.add_row(
                Text(glyph, style=GM_MUTED),
                Text(stage.upper()),
                Text(STATUS_PENDING, style=_STATUS_STYLES[STATUS_PENDING]),
                Text("—", style=GM_MUTED),
                key=stage,
            )
        self.query_one("#deploy-run-events", RichLog).write(
            f"{_WAIT_MARK} DEPLOY STARTING · STACK {self.config.stack_name.upper()} "
            f"· TIER {self.config.tier.upper()} · REGION {self.config.region.upper()}",
        )
        self._run_deploy()

    def on_unmount(self) -> None:
        self._ui_closed.set()
        self._stream_stop.set()

    def action_request_dismiss(self) -> None:
        if self._deploy_running and not self._dismiss_armed:
            self._dismiss_armed = True
            self._write_log(f"{_WARN_MARK} DEPLOY STILL RUNNING · ESC AGAIN TO DETACH")
            return
        self._ui_closed.set()
        self._stream_stop.set()
        self.dismiss(None)

    # ------------------------------------------------------- deploy worker --

    @work(thread=True, exclusive=True, group="deploy-exec")
    def _run_deploy(self) -> None:
        """Run the blocking executor off the UI thread; forward the outcome."""
        try:
            state = self._executor(self.config, self._emit_from_thread)
        except RuntimeError as exc:  # includes OrchestrationError
            self._call_ui(self._on_deploy_failed, str(exc))
        else:
            self._call_ui(self._on_deploy_complete, state)

    def _emit_from_thread(self, event: ProgressEvent) -> None:
        """ProgressCallback: worker thread -> UI thread, dropped once closed."""
        self._call_ui(self._apply_event, event)

    def _call_ui(self, callback: Callable[..., None], *args: object) -> None:
        if self._ui_closed.is_set():
            return
        try:
            self.app.call_from_thread(callback, *args)
        except RuntimeError:
            # App shut down between the check and the call; nothing to update.
            return

    # ------------------------------------------------------- stream worker --

    @work(thread=True, exclusive=True, group="userdata-stream")
    def _run_userdata_stream(self, instance_id: str) -> None:
        """Iterate the blocking userdata log stream; append lines to the log."""
        self._call_ui(self._write_log, f"{_OK_MARK} USERDATA STREAM ATTACHED · {instance_id}")
        try:
            stream = self._userdata_streamer(instance_id)
        except RuntimeError as exc:
            self._call_ui(self._write_log, f"{_ERROR_MARK} USERDATA STREAM FAILED · {escape(str(exc))}")
            return
        detached = False
        try:
            for line in stream:
                if self._stream_stop.is_set() or self._ui_closed.is_set():
                    detached = True
                    break
                self._call_ui(self._write_log, f"[dim]\\[USERDATA][/dim] {escape(line)}")
        except RuntimeError as exc:
            self._call_ui(self._write_log, f"{_ERROR_MARK} USERDATA STREAM FAILED · {escape(str(exc))}")
            return
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
        if detached:
            self._call_ui(self._write_log, f"{_WARN_MARK} USERDATA STREAM DETACHED")
            return
        # SSMService ends the stream on the completion marker/guard (SUCCESS),
        # the error guard (ERROR), or the 600s timeout (TIMEOUT) — render the
        # actual outcome, never a blanket "OK" for error/timeout.
        from geusemaker.services.ssm import UserdataCompletion

        completion = getattr(stream, "completion", None)
        if completion == UserdataCompletion.ERROR:
            self._call_ui(
                self._write_log,
                f"{_ERROR_MARK} USERDATA INITIALIZATION FAILED · {instance_id}",
            )
        elif completion == UserdataCompletion.TIMEOUT:
            self._call_ui(
                self._write_log,
                f"{_WARN_MARK} USERDATA STREAM TIMED OUT · {instance_id}",
            )
        else:
            self._call_ui(self._write_log, f"{_OK_MARK} USERDATA STREAM ENDED · {instance_id}")

    def _maybe_start_userdata_stream(self) -> None:
        if self._stream_started or self._ui_closed.is_set():
            return
        if self._instance_id is None:
            self._write_log(f"{_WAIT_MARK} INSTANCE ID UNKNOWN · USERDATA STREAM SKIPPED")
            return
        self._stream_started = True
        self._run_userdata_stream(self._instance_id)

    # ------------------------------------------------------- UI mutations --

    def _apply_event(self, event: ProgressEvent) -> None:
        """Apply one ProgressEvent to the timeline and the event log."""
        if self._ui_closed.is_set() or not self.is_mounted:
            return
        stage = event.stage
        if stage in self.stage_statuses:
            if event.level == "error":
                self._set_stage(stage, STATUS_ERROR)
            elif self.stage_statuses[stage] != STATUS_ERROR:
                if (
                    self._active_stage is not None
                    and self._active_stage != stage
                    and self.stage_statuses.get(self._active_stage) == STATUS_ACTIVE
                ):
                    self._set_stage(self._active_stage, STATUS_DONE)
                self._set_stage(stage, STATUS_ACTIVE)
                self._active_stage = stage
        if event.resource_id:
            self._stage_resources[stage] = event.resource_id
            if stage == "ec2":
                self._instance_id = event.resource_id
            self._set_resource(stage, event.resource_id)
        if event.level == "error":
            self._write_log(f"{_ERROR_MARK} \\[{stage.upper()}] [{GM_FAULT}]{escape(event.message)}[/{GM_FAULT}]")
        elif event.level == "warn":
            self._write_log(f"{_WARN_MARK} \\[{stage.upper()}] {escape(event.message)}")
        else:
            self._write_log(f"\\[{stage.upper()}] {escape(event.message)}")
        if stage == "userdata":
            self._maybe_start_userdata_stream()

    def _on_deploy_complete(self, state: DeploymentState) -> None:
        """Success terminal state: banner + every non-error stage DONE."""
        self._deploy_running = False
        self._stream_stop.set()
        if not self.is_mounted:
            return
        for stage in self.stages:
            if self.stage_statuses[stage] != STATUS_ERROR:
                self._set_stage(stage, STATUS_DONE)
        banner = f"DEPLOY COMPLETE · STACK {state.stack_name.upper()}"
        self.query_one("#deploy-run-status", Static).update(f"[bold {GM_SIGNAL}]{banner}[/bold {GM_SIGNAL}]")
        self._write_log(f"{_OK_MARK} {banner}")

    def _on_deploy_failed(self, message: str) -> None:
        """Failure terminal state: banner + current stage ERROR; stay open."""
        self._deploy_running = False
        self._stream_stop.set()
        if not self.is_mounted:
            return
        if self._active_stage is not None and self.stage_statuses.get(self._active_stage) == STATUS_ACTIVE:
            self._set_stage(self._active_stage, STATUS_ERROR)
        banner = f"DEPLOY FAILED · {escape(message)}"
        self.query_one("#deploy-run-status", Static).update(f"[bold {GM_FAULT}]{banner}[/bold {GM_FAULT}]")
        self._write_log(f"{_ERROR_MARK} {banner}")
        self._write_log(f"{_WARN_MARK} SCREEN LEFT OPEN FOR READING · ESC TO CLOSE")

    def _set_stage(self, stage: Stage, status: str) -> None:
        self.stage_statuses[stage] = status
        table = self.query_one("#deploy-run-timeline", DataTable)
        table.update_cell(stage, self._col_keys[2], Text(status, style=_STATUS_STYLES[status]))

    def _set_resource(self, stage: Stage, resource_id: str) -> None:
        if stage not in self.stage_statuses:
            return
        table = self.query_one("#deploy-run-timeline", DataTable)
        table.update_cell(stage, self._col_keys[3], Text(resource_id))

    def _write_log(self, line: str) -> None:
        if not self.is_mounted:
            return
        self.query_one("#deploy-run-events", RichLog).write(line)


__all__ = [
    "EVENT_LOG_MAX_LINES",
    "STAGE_ORDER",
    "DeployExecutor",
    "DeployRunScreen",
    "UserdataStreamer",
    "default_executor",
    "default_userdata_streamer",
    "stages_for_config",
]
