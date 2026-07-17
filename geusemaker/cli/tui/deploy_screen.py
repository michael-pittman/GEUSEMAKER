"""Deploy configuration form driven by the UI-neutral configuration seam.

Every form decision routes through :class:`~geusemaker.cli.configuration.ConfigBuilder`
and :class:`~geusemaker.cli.configuration.DeploymentDraft`: which fields render
(``visible_fields()``), what a value means (``set()`` with Pydantic assignment
validation), what is wrong (``validate()``), and what would deploy
(``build()`` / ``to_yaml()``). The screen performs no AWS or network calls and
never executes a deployment — its terminal act is posting
:class:`DeployScreen.LaunchRequested` carrying a validated ``DeploymentConfig``;
the hosting app decides what to do with it.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import UnionType
from typing import Any, ClassVar, Literal, Union, get_args, get_origin

from pydantic import ValidationError
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Input, Label, Select, Static

from geusemaker.cli.configuration import ConfigBuilder, DeploymentDraft
from geusemaker.config import ConfigurationError
from geusemaker.models import DeploymentConfig

#: Draft fields whose value changes conditional visibility of other fields.
VISIBILITY_TRIGGERS: frozenset[str] = frozenset({"setup_mode", "tier", "enable_https", "workload"})

#: Visual grouping of every editable draft field (preview metadata excluded).
FIELD_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("IDENTITY", ("stack_name", "region", "setup_mode")),
    ("TOPOLOGY", ("tier", "workload", "instance_preference")),
    ("COMPUTE", ("instance_type", "use_spot", "os_type", "architecture", "ami_type", "ami_id")),
    (
        "HTTPS",
        (
            "enable_https",
            "tier1_use_self_signed",
            "alb_domain_name",
            "alb_hosted_zone_id",
            "alb_certificate_arn",
            "cloudfront_certificate_arn",
            "force_https_redirect",
        ),
    ),
    (
        "NETWORKING",
        (
            "vpc_id",
            "subnet_id",
            "public_subnet_ids",
            "private_subnet_ids",
            "storage_subnet_id",
            "security_group_id",
            "efs_id",
            "keypair_name",
            "attach_internet_gateway",
            "create_mount_target",
        ),
    ),
    (
        "OPTIONS",
        (
            "budget_limit",
            "use_runtime_bundle",
            "runtime_bundle_path",
            "enable_alb",
            "enable_cdn",
            "auto_rollback_on_failure",
            "rollback_timeout_minutes",
        ),
    ),
)

_SIGNAL = "bold #c8f542"
_FAULT = "bold #ff4d4d"

#: Textual 8.x blank-select sentinel type (``Select.NULL`` is a ``NoSelection``).
_NO_SELECTION = type(Select.NULL)

FieldKind = Literal["select", "bool", "list", "text"]


def _flatten_annotation(annotation: Any) -> tuple[Any, ...]:
    """Flatten nested Union/Optional annotations into their member types."""
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        flat: list[Any] = []
        for arg in get_args(annotation):
            flat.extend(_flatten_annotation(arg))
        return tuple(flat)
    return (annotation,)


def _literal_values(annotation: Any) -> tuple[str, ...]:
    """Collect Literal choice values from a (possibly Optional) annotation."""
    values: list[str] = []
    for part in _flatten_annotation(annotation):
        if get_origin(part) is Literal:
            values.extend(str(choice) for choice in get_args(part))
    return tuple(dict.fromkeys(values))


def _classify(name: str) -> FieldKind:
    """Map a draft field to its widget kind from the model annotation."""
    annotation = DeploymentDraft.model_fields[name].annotation
    if _literal_values(annotation):
        return "select"
    parts = _flatten_annotation(annotation)
    if bool in parts:
        return "bool"
    if any(get_origin(part) is list for part in parts):
        return "list"
    return "text"


#: Widget kind per rendered field, derived once from the draft annotations.
FIELD_KINDS: dict[str, FieldKind] = {name: _classify(name) for _, fields in FIELD_GROUPS for name in fields}


def _placeholder(name: str, kind: FieldKind) -> str:
    """Placeholder text: the config default, AUTO for optional, REQUIRED otherwise."""
    info = DeploymentConfig.model_fields.get(name)
    if info is None:
        return "OPTIONAL"
    if info.is_required():
        return "REQUIRED"
    default = info.get_default(call_default_factory=True)
    if default is None:
        return "COMMA-SEPARATED · AUTO" if kind == "list" else "AUTO"
    return f"DEFAULT · {default}"


class DeployScreen(Screen[None]):
    """Brutalist deploy form: draft editing, validation, YAML round-trip, launch."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "close", "BACK"),
        Binding("ctrl+l", "launch", "LAUNCH"),
        Binding("ctrl+e", "export_yaml", "EXPORT YAML"),
        Binding("ctrl+o", "import_yaml", "IMPORT YAML"),
        Binding("v", "validate_draft", "VALIDATE"),
    ]

    # NOTE: Textual does not expose app-stylesheet variables to DEFAULT_CSS,
    # so the $gm-* tokens are redeclared here with the brutalist.tcss values.
    DEFAULT_CSS = """
    $gm-surface: #0a0c0f;
    $gm-panel: #12151a;
    $gm-ink: #e8ecef;
    $gm-muted: #6b7280;
    $gm-signal: #c8f542;
    $gm-warn: #f5a524;
    $gm-fault: #ff4d4d;
    $gm-rule: #2a3038;

    DeployScreen {
        background: $gm-surface;
        color: $gm-ink;
    }
    #deploy-workspace {
        height: 1fr;
    }
    #deploy-form {
        width: 1fr;
        background: $gm-panel;
        border: heavy $gm-rule;
        padding: 0 1;
    }
    #deploy-form-title {
        height: 3;
        padding: 0 1;
        border: heavy $gm-signal;
        color: $gm-signal;
        text-style: bold;
    }
    .group-title {
        height: 1;
        margin-top: 1;
        color: $gm-signal;
        text-style: bold;
    }
    .field-row {
        height: auto;
    }
    .field-label {
        color: $gm-muted;
    }
    .field-error {
        display: none;
        color: $gm-fault;
        text-style: bold;
    }
    #deploy-side {
        width: 56;
        border: heavy $gm-rule;
        padding: 0 1;
    }
    #deploy-preview-title, #deploy-validation-title {
        height: 3;
        padding: 0 1;
        border: heavy $gm-signal;
        color: $gm-signal;
        text-style: bold;
    }
    #deploy-preview-scroll {
        height: 1fr;
        border: heavy $gm-rule;
        padding: 0 1;
    }
    #deploy-validation-scroll {
        height: 1fr;
        border: heavy $gm-rule;
        padding: 0 1;
    }
    #deploy-import-path {
        display: none;
        border: heavy $gm-warn;
    }
    #deploy-status {
        height: 2;
        padding: 0 1;
        color: $gm-muted;
    }
    #deploy-actions {
        height: auto;
    }
    #deploy-actions Button {
        margin-right: 1;
    }
    """

    class LaunchRequested(Message):
        """Request the hosting app to execute a deployment for a built config."""

        def __init__(self, config: DeploymentConfig) -> None:
            self.config = config
            super().__init__()

    def __init__(
        self,
        *,
        initial_state: Mapping[str, Any] | None = None,
        config_path: Path | None = None,
    ) -> None:
        super().__init__()
        if config_path is not None:
            self._builder = ConfigBuilder.from_yaml(config_path)
        else:
            self._builder = ConfigBuilder.from_initial_state(initial_state or {})

    @property
    def builder(self) -> ConfigBuilder:
        """Return the live builder backing the form (read for state, not mutation)."""
        return self._builder

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Horizontal(id="deploy-workspace"):
            with VerticalScroll(id="deploy-form"):
                yield Static("DEPLOY · CONFIGURATION", id="deploy-form-title")
                for group, fields in FIELD_GROUPS:
                    yield Static(f"█ {group}", id=f"group-title-{group.lower()}", classes="group-title")
                    for name in fields:
                        with Vertical(id=f"field-row-{name}", classes="field-row"):
                            kind = FIELD_KINDS[name]
                            if kind != "bool":
                                yield Label(name.upper().replace("_", " "), classes="field-label")
                            yield self._make_widget(name, kind)
                            yield Static("", id=f"field-error-{name}", classes="field-error")
            with Vertical(id="deploy-side"):
                yield Static("PREVIEW · YAML", id="deploy-preview-title")
                with VerticalScroll(id="deploy-preview-scroll"):
                    yield Static("", id="deploy-preview")
                yield Static("VALIDATION", id="deploy-validation-title")
                with VerticalScroll(id="deploy-validation-scroll"):
                    yield Static("PRESS V TO VALIDATE · CTRL+L TO LAUNCH", id="deploy-validation")
                yield Input(placeholder="PATH TO CONFIG YAML · ENTER TO IMPORT", id="deploy-import-path")
                yield Static("", id="deploy-status")
                with Horizontal(id="deploy-actions"):
                    yield Button("LAUNCH ^L", id="deploy-launch")
                    yield Button("VALIDATE V", id="deploy-validate")
                    yield Button("EXPORT ^E", id="deploy-export")
                    yield Button("IMPORT ^O", id="deploy-import")

    def _make_widget(self, name: str, kind: FieldKind) -> Select[str] | Checkbox | Input:
        field_id = f"field-{name}"
        if kind == "select":
            choices = _literal_values(DeploymentDraft.model_fields[name].annotation)
            options = [(choice, choice) for choice in choices]
            return Select(options, allow_blank=True, prompt="UNSET", id=field_id)
        if kind == "bool":
            return Checkbox(name.upper().replace("_", " "), id=field_id)
        return Input(placeholder=_placeholder(name, kind), id=field_id)

    def on_mount(self) -> None:
        with self.prevent(Input.Changed, Select.Changed, Checkbox.Changed):
            self._sync_widgets()
        self._refresh_visibility()
        self._refresh_preview()

    # ------------------------------------------------------------------
    # Builder → widgets
    # ------------------------------------------------------------------
    def _sync_widgets(self) -> None:
        """Push the current draft values into every field widget."""
        draft = self._builder.draft
        for name, kind in FIELD_KINDS.items():
            value = getattr(draft, name)
            if kind == "select":
                select = self.query_one(f"#field-{name}", Select)
                select.value = str(value) if value is not None else Select.NULL
            elif kind == "bool":
                checkbox = self.query_one(f"#field-{name}", Checkbox)
                if value is None:
                    info = DeploymentConfig.model_fields.get(name)
                    default = info.get_default(call_default_factory=True) if info is not None else False
                    checkbox.value = bool(default) if default is not None else False
                else:
                    checkbox.value = bool(value)
            else:
                text_input = self.query_one(f"#field-{name}", Input)
                if value is None:
                    text_input.value = ""
                elif kind == "list":
                    text_input.value = ", ".join(str(item) for item in value)
                else:
                    text_input.value = str(value)

    def _refresh_visibility(self) -> None:
        """Re-evaluate builder.visible_fields() and show/hide rows and groups."""
        visible = set(self._builder.visible_fields())
        for group, fields in FIELD_GROUPS:
            any_visible = False
            for name in fields:
                row = self.query_one(f"#field-row-{name}", Vertical)
                show = name in visible
                row.display = show
                any_visible = any_visible or show
            self.query_one(f"#group-title-{group.lower()}", Static).display = any_visible

    def _refresh_preview(self) -> None:
        """Render the live YAML preview, or an explicit INCOMPLETE marker."""
        preview = self.query_one("#deploy-preview", Static)
        errors = self._builder.validate()
        if errors:
            count = sum(len(messages) for messages in errors.values())
            preview.update(Text(f"INCOMPLETE · {count} ERRORS", style=_FAULT))
            return
        try:
            text = ConfigBuilder(self._builder.draft.model_copy(deep=True)).to_yaml()
        except (ValidationError, ConfigurationError) as exc:
            preview.update(Text(f"PREVIEW UNAVAILABLE · {exc}", style=_FAULT))
            return
        preview.update(Text(text))

    # ------------------------------------------------------------------
    # Widgets → builder
    # ------------------------------------------------------------------
    def on_input_changed(self, event: Input.Changed) -> None:
        widget_id = event.input.id or ""
        if widget_id.startswith("field-"):
            self._apply_field(widget_id.removeprefix("field-"), event.value)

    def on_select_changed(self, event: Select.Changed) -> None:
        widget_id = event.select.id or ""
        if widget_id.startswith("field-"):
            self._apply_field(widget_id.removeprefix("field-"), event.value)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        widget_id = event.checkbox.id or ""
        if widget_id.startswith("field-"):
            self._apply_field(widget_id.removeprefix("field-"), event.value)

    def _apply_field(self, name: str, value: object) -> None:
        """Coerce a widget value and set it on the builder; never crash on bad input."""
        error_slot = self.query_one(f"#field-error-{name}", Static)
        try:
            self._builder.set(name, self._coerce(name, value))
        except (ValidationError, ValueError) as exc:
            error_slot.update(Text(f"INVALID · {self._error_text(exc)}", style=_FAULT))
            error_slot.display = True
            return
        error_slot.update("")
        error_slot.display = False
        if name in VISIBILITY_TRIGGERS:
            self._refresh_visibility()
        self._refresh_preview()

    def _coerce(self, name: str, value: object) -> Any:
        """Convert raw widget output to a draft value; blanks mean unset."""
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, _NO_SELECTION):
            return None
        text = str(value).strip()
        if not text:
            return None
        if FIELD_KINDS[name] == "list":
            items = [part.strip() for part in text.split(",") if part.strip()]
            return items or None
        # int/Decimal/str coercion is delegated to Pydantic assignment
        # validation inside ConfigBuilder.set (ValidationError on failure).
        return text

    @staticmethod
    def _error_text(exc: Exception) -> str:
        if isinstance(exc, ValidationError) and exc.errors():
            return str(exc.errors()[0].get("msg", "invalid value"))
        return str(exc)

    # ------------------------------------------------------------------
    # Validation pane
    # ------------------------------------------------------------------
    def _render_validation(self, errors: dict[str, list[str]]) -> None:
        pane = self.query_one("#deploy-validation", Static)
        if not errors:
            pane.update(Text("VALID · READY TO LAUNCH", style=_SIGNAL))
            return
        report = Text()
        for field, messages in errors.items():
            for message in messages:
                report.append(f"{field.upper()}\n", style=_FAULT)
                report.append(f"  {message}\n", style="#e8ecef")
        pane.update(report)

    @staticmethod
    def _error_count(errors: dict[str, list[str]]) -> int:
        return sum(len(messages) for messages in errors.values())

    def _set_status(self, message: str, *, error: bool = False) -> None:
        style = _FAULT if error else _SIGNAL
        self.query_one("#deploy-status", Static).update(Text(message, style=style))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def action_close(self) -> None:
        self.dismiss(None)

    def action_validate_draft(self) -> None:
        errors = self._builder.validate()
        self._render_validation(errors)
        if errors:
            self._set_status(f"INVALID · {self._error_count(errors)} ERRORS", error=True)
        else:
            self._set_status("VALID · READY TO LAUNCH")

    def action_launch(self) -> None:
        """Validate, then build and post LaunchRequested. Never posts when invalid."""
        errors = self._builder.validate()
        self._render_validation(errors)
        if errors:
            self._set_status(f"LAUNCH BLOCKED · {self._error_count(errors)} VALIDATION ERRORS", error=True)
            return
        try:
            config = ConfigBuilder(self._builder.draft.model_copy(deep=True)).build()
        except (ValidationError, ConfigurationError) as exc:
            self._set_status(f"LAUNCH BLOCKED · {exc}", error=True)
            return
        self.post_message(self.LaunchRequested(config))
        self._set_status(f"LAUNCH REQUESTED · {config.stack_name}")

    def action_export_yaml(self) -> None:
        """Write the built config to <stack_name>.yaml in the current directory."""
        errors = self._builder.validate()
        if errors:
            self._render_validation(errors)
            self._set_status(f"EXPORT BLOCKED · {self._error_count(errors)} VALIDATION ERRORS", error=True)
            return
        try:
            text = ConfigBuilder(self._builder.draft.model_copy(deep=True)).to_yaml()
        except (ValidationError, ConfigurationError) as exc:
            self._set_status(f"EXPORT BLOCKED · {exc}", error=True)
            return
        path = Path.cwd() / f"{self._builder.draft.stack_name}.yaml"
        try:
            path.write_text(text, encoding="utf-8")
        except OSError as exc:
            self._set_status(f"EXPORT FAILED · {exc}", error=True)
            return
        self._set_status(f"EXPORTED · {path}")

    def action_import_yaml(self) -> None:
        """Reveal the inline import-path input."""
        path_input = self.query_one("#deploy-import-path", Input)
        path_input.display = True
        path_input.focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "deploy-import-path":
            return
        path_input = event.input
        raw = event.value.strip()
        if not raw:
            path_input.display = False
            return
        try:
            imported = ConfigBuilder.from_yaml(Path(raw))
        except (ConfigurationError, ValidationError) as exc:
            self._set_status(f"IMPORT FAILED · {exc}", error=True)
            return
        self._builder = imported
        with self.prevent(Input.Changed, Select.Changed, Checkbox.Changed):
            self._sync_widgets()
        for name in FIELD_KINDS:
            error_slot = self.query_one(f"#field-error-{name}", Static)
            error_slot.update("")
            error_slot.display = False
        self._refresh_visibility()
        self._refresh_preview()
        self._render_validation(self._builder.validate())
        path_input.value = ""
        path_input.display = False
        self._set_status(f"IMPORTED · {raw}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        actions = {
            "deploy-launch": self.action_launch,
            "deploy-validate": self.action_validate_draft,
            "deploy-export": self.action_export_yaml,
            "deploy-import": self.action_import_yaml,
        }
        action = actions.get(event.button.id or "")
        if action is not None:
            action()


__all__ = ["DeployScreen", "FIELD_GROUPS", "FIELD_KINDS", "VISIBILITY_TRIGGERS"]
