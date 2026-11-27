import subprocess
from pathlib import Path

import pytest

import benchmark_runner
from jpamb.evaluation import (
    ComponentSettings,
    EvaluationRun,
    MethodMeasurement,
    append_run,
    load_runs,
)


@pytest.mark.parametrize("method_timeout", [None, 20.0])
def test_run_single_uses_cli_settings_and_structured_results(monkeypatch, method_timeout):
    settings = ComponentSettings(static=False, dynamic_structure=False)
    official = {"total_score": 2.75}
    measured = EvaluationRun("measured", settings, 2, "success", official=official)

    for variable in settings.environment():
        monkeypatch.setenv(variable, "1")

    def execute(command, env, timeout):
        assert command[:4] == [benchmark_runner.sys.executable, "-m", "cli", "analyse"]
        assert command[command.index("--iterations") + 1] == "2"
        assert "--no-static" in command
        assert "--no-dynamic-structure" in command
        assert "--no-dictionary" not in command
        assert "--no-syntactic-structure" not in command
        assert command[command.index("--filter") + 1] == "Simple.*"
        assert command[-2:] == ["--", "dynamic-coverage-analysis"]
        assert timeout == 2
        if method_timeout is None:
            assert "--timeout" not in command
        else:
            assert float(command[command.index("--timeout") + 1]) == method_timeout
        assert not settings.environment().keys() & env.keys()
        # This disagrees with the structured result, so scraping would fail.
        return 0, "Total 0.01 12.0 Db 0.001 s"

    monkeypatch.setattr(benchmark_runner, "execute_analysis", execute)
    monkeypatch.setattr(benchmark_runner, "load_runs", lambda path: [measured])

    run = benchmark_runner.run_single(
        "dynamic-coverage-analysis",
        settings,
        iterations=2,
        repetition=7,
        filter_pattern="Simple.*",
        timeout=2,
        method_timeout=method_timeout,
    )

    assert run.run_id == "measured"
    assert run.status == "success"
    assert run.repetition == 7
    assert run.elapsed_seconds >= 0
    assert run.official == official


@pytest.mark.parametrize("status", ["failed", "timeout"])
def test_run_single_preserves_partial_export_when_command_fails(monkeypatch, status):
    settings = ComponentSettings()
    measured = EvaluationRun("measured", settings, 1, status, error="a method failed")
    monkeypatch.setattr(
        benchmark_runner, "execute_analysis", lambda *args: (3, "analysis error")
    )
    monkeypatch.setattr(benchmark_runner, "load_runs", lambda path: [measured])

    run = benchmark_runner.run_single(
        "dynamic-coverage-analysis", settings, iterations=1, repetition=2
    )

    assert run.run_id == "measured"
    assert run.status == status
    assert run.repetition == 2
    assert "exited with status 3" in run.error
    assert "analysis error" in run.error
    assert "a method failed" in run.error


@pytest.mark.parametrize("status", ["failed", "timeout"])
def test_run_single_records_runs_without_an_export(monkeypatch, status):
    def execute(command, env, timeout):
        if status == "timeout":
            raise subprocess.TimeoutExpired(command, timeout)
        return 4, "setup failed"

    monkeypatch.setattr(benchmark_runner, "execute_analysis", execute)

    run = benchmark_runner.run_single(
        "dynamic-coverage-analysis",
        ComponentSettings(),
        iterations=1,
        repetition=1,
        timeout=1.5,
    )

    assert run.status == status
    assert run.run_id
    assert not run.measurements
    assert run.official is None
    assert run.elapsed_seconds >= 0
    assert ("1.5 seconds" if status == "timeout" else "setup failed") in run.error


def test_runner_saves_repetitions_and_rebuilds_without_running(
    monkeypatch, tmp_path, capsys
):
    invocations = []

    def run_single(analysis, settings, *, iterations, repetition, **kwargs):
        invocations.append((settings, iterations, repetition, kwargs["method_timeout"]))
        return EvaluationRun(
            f"run-{len(invocations)}",
            settings,
            iterations,
            "failed" if repetition == 1 else "timeout",
            elapsed_seconds=0.1,
            repetition=repetition,
            error="test failure",
        )

    monkeypatch.setattr(benchmark_runner, "run_single", run_single)
    raw = tmp_path / "arbitrary-name.csv"
    report = tmp_path / "reports" / "matrix.md"

    benchmark_runner.main(
        [
            "--repetitions",
            "2",
            "--jpamb-iterations",
            "4",
            "--method-timeout",
            "20",
            "--config",
            "all-enabled",
            "--config",
            "no-static,no-dictionary",
            "--csv",
            str(raw),
            "--output",
            str(report),
        ]
    )

    assert invocations == [
        (ComponentSettings(), 4, 1, 20.0),
        (ComponentSettings(), 4, 2, 20.0),
        (ComponentSettings(static=False, dictionary=False), 4, 1, 20.0),
        (ComponentSettings(static=False, dictionary=False), 4, 2, 20.0),
    ]
    runs = load_runs(raw)
    assert [run.run_id for run in runs] == [f"run-{i}" for i in range(1, 5)]
    assert [run.status for run in runs] == ["failed", "timeout", "failed", "timeout"]
    assert [run.repetition for run in runs] == [1, 2, 1, 2]
    assert capsys.readouterr().out.count("\n  Repetition ") == 4
    first_report = report.read_text(encoding="utf-8")

    monkeypatch.setattr(
        benchmark_runner,
        "run_single",
        lambda *_args, **_kwargs: pytest.fail("reran JPAMB"),
    )
    benchmark_runner.main(["--from-saved", str(raw), "--output", str(report)])

    assert report.read_text(encoding="utf-8") == first_report
    assert capsys.readouterr().out == first_report


def test_runner_rebuilds_html_from_saved_measurements(monkeypatch, tmp_path, capsys):
    raw = tmp_path / "measurements.csv"
    report = tmp_path / "reports" / "comparison.html"
    method = "jpamb.cases.Simple.assertBoolean:(Z)V"
    settings = ComponentSettings()
    append_run(
        raw,
        EvaluationRun(
            "successful-run",
            settings,
            1,
            "success",
            measurements=(
                MethodMeasurement(
                    method=method,
                    iteration=1,
                    covered_instructions=3,
                    total_instructions=4,
                    observed_outcomes=("ok",),
                    analysis_seconds=0.25,
                ),
            ),
            expected_methods=(method,),
        ),
    )
    diagnostic = "<script>unsafe()</script>"
    append_run(raw, EvaluationRun("failed-run", settings, 1, "failed", error=diagnostic))

    monkeypatch.setattr(
        benchmark_runner,
        "run_single",
        lambda *_args, **_kwargs: pytest.fail("reran JPAMB"),
    )
    benchmark_runner.main(
        ["--from-saved", str(raw), "--all-methods", "--output", str(report)]
    )

    html = report.read_text(encoding="utf-8")
    assert html.lower().startswith("<!doctype html>")
    assert "<table" in html
    assert "75.000%" in html
    assert method in html
    assert diagnostic not in html
    assert "&lt;script&gt;unsafe()&lt;/script&gt;" in html
    assert capsys.readouterr().out == f"Saved comparison table to {report}\n"


def test_default_matrix_has_all_configurations(monkeypatch, capsys):
    invocations = []

    def run_single(analysis, settings, *, iterations, repetition, **kwargs):
        invocations.append((settings, iterations, repetition))
        return EvaluationRun(
            f"run-{len(invocations)}",
            settings,
            iterations,
            "failed",
            elapsed_seconds=0.2,
            repetition=repetition,
        )

    monkeypatch.setattr(benchmark_runner, "run_single", run_single)

    benchmark_runner.main(["-n", "1"])

    assert len({settings for settings, _, _ in invocations}) == 16
    assert all(
        iterations == 3 and repetition == 1 for _, iterations, repetition in invocations
    )
    assert "[16/16]" in capsys.readouterr().out


@pytest.mark.parametrize("suffix", [".csv", ".runs.jsonl"])
def test_report_cannot_overwrite_raw_files(tmp_path, suffix):
    raw = tmp_path / "raw.csv"
    protected_path = Path(raw.with_suffix(suffix))

    with pytest.raises(SystemExit) as error:
        benchmark_runner.main(
            ["--from-saved", str(raw), "--output", str(protected_path)]
        )

    assert error.value.code == 2
