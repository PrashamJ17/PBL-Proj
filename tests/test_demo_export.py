"""The demo export must behave the way the demo video says it does."""

from retainiq.cli import main
from retainiq.experiments.demo_export import write_demo_export


def test_raw_demo_export_is_blocked_because_amounts_are_cents(tmp_path, capsys):
    c, s = write_demo_export(tmp_path)
    assert main(["preflight", "--customers", str(c), "--subscriptions", str(s)]) == 1
    assert "BLOCKED" in capsys.readouterr().out


def test_demo_export_produces_a_report_once_units_are_corrected(tmp_path):
    c, s = write_demo_export(tmp_path)
    out = tmp_path / "report.html"
    code = main(["autopsy", "--customers", str(c), "--subscriptions", str(s),
                 "--divide-amounts-by", "100", "--interval", "month",
                 "--name", "Demo", "--out", str(out)])
    assert code == 0 and out.exists()


def test_demo_export_matches_the_figures_the_demo_materials_quote(tmp_path):
    """The slides, storyboard and video cite these numbers from this export. If the
    generator's random stream changes, they silently stop being true -- which happened
    once, when the cancellation dates were drawn before the amounts."""
    import pandas as pd
    from test_preflight_cli import _stripe

    _, s = write_demo_export(tmp_path)
    subs = pd.read_csv(s)
    assert subs["Plan Amount"].iloc[0] == 18922
    # 15,311.5 exactly; preflight prints it rounded, as "15,312", and 153.12 once divided.
    assert subs["Plan Amount"].median() == 15311.5
    _, fixture = _stripe(n=400, seed=0, cents=True)
    assert subs["Plan Amount"].tolist() == fixture["Plan Amount"].tolist()


def test_demo_export_is_byte_identical_across_runs(tmp_path):
    a = write_demo_export(tmp_path / "a")
    b = write_demo_export(tmp_path / "b")
    assert all(x.read_bytes() == y.read_bytes() for x, y in zip(a, b, strict=True))
