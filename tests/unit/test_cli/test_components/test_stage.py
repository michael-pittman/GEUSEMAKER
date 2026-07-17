from geusemaker.cli.components.stage import render_stage
from geusemaker.cli.progress_events import ProgressEvent


def test_stage_renders_label_and_message():
    rendered = render_stage(ProgressEvent("efs", "Creating filesystem"))
    assert "STAGE · EFS" in rendered.plain
    assert "Creating filesystem" in rendered.plain


def test_stage_has_ascii_fallback():
    rendered = render_stage(ProgressEvent("ec2", "Launching"), unicode=False)
    assert rendered.plain == "[EC2] Launching"
