import json
import subprocess
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import cli
import jpamb
import jvm
import sexpr
from jpamb.evaluation import MEASUREMENT_ENV, ComponentSettings, load_runs
from jpamb.utils import Effect

METHODS = ("example.Test.first:()V", "example.Test.second:(Ljpamb/utils/Smith;)V")


@pytest.fixture
def evaluation_suite(monkeypatch, tmp_path):
    benchmark = jpamb.Benchmark(
        OrderedDict(
            (
                jpamb.Experiment(jvm.AbsMethodID.decode(method), None),
                jpamb.Control(OrderedDict(), {"ok"}),
            )
            for method in METHODS
        )
    )
    concrete = jpamb.Experiment(jvm.AbsMethodID.decode(METHODS[0]), jpamb.Input(()))
    benchmark.experiments[concrete] = jpamb.Control(OrderedDict(), {"ok"})
    suite = tmp_path / "suite"
    suite.mkdir()
    monkeypatch.setattr(jpamb.Suite, "benchmark", lambda self, *, eff: benchmark)
    info_calls = []

    def info(_effect, command, *, cwd, env, timeout):
        assert command == ("dynamic-coverage-analysis", "info")
        assert cwd == suite
        assert MEASUREMENT_ENV not in env
        info_calls.append(ComponentSettings.from_environment(env))
        return "dynamic\n1.0\nBit Diddlers\ndynamic,python\n"

    monkeypatch.setattr(Effect, "run", info)
    return suite, benchmark, info_calls


def prediction_experiment(method, env, value):
    Path(env[MEASUREMENT_ENV]).write_text(
        json.dumps(
            {
                "method": method,
                "configuration": asdict(ComponentSettings.from_environment(env)),
                "covered_instructions": value,
                "total_instructions": 10,
                "observed_outcomes": ["ok"] if value % 2 else ["ok", "*"],
                "analysis_seconds": value / 100,
            }
        ),
        encoding="utf-8",
    )
    predictions = {query: -1 for query in jpamb.QUERIES}
    predictions.update({"ok": value, "assertion error": "category", "*": "category"})
    return SimpleNamespace(
        output="\n".join(
            f"{query};{prediction}" for query, prediction in predictions.items()
        ),
        time_ns=value * 1_000_000,
        time_relative=value / 2,
        calibrations_ns=[100_000, 200_000],
    )


def invoke(suite, *options):
    return CliRunner().invoke(
        cli.cli,
        ["--workdir", str(suite), "analyse", "dynamic-coverage-analysis", *options],
        catch_exceptions=False,
    )


@pytest.mark.parametrize(
    ("flag", "key"),
    [
        ("--no-static", "static"),
        ("--no-dictionary", "dictionary"),
        ("--no-syntactic-structure", "syntactic_structure"),
        ("--no-dynamic-structure", "dynamic_structure"),
    ],
)
def test_independent_flags_reach_the_analyzer(monkeypatch, evaluation_suite, flag, key):
    suite, _, info_calls = evaluation_suite
    for variable in ComponentSettings().environment():
        monkeypatch.setenv(variable, "0")
    monkeypatch.setenv(MEASUREMENT_ENV, "stale-path")
    experiment_calls = []

    def experiment(_effect, command, *, env, **kwargs):
        experiment_calls.append(ComponentSettings.from_environment(env))
        return prediction_experiment(command[1], env, 1)

    monkeypatch.setattr(Effect, "experiment", experiment)
    result = invoke(suite, "--iterations", "1", flag)
    assert result.exit_code == 0, result.output
    selected = ComponentSettings(**{key: False})
    assert info_calls == [selected]
    assert experiment_calls == [selected, selected]
    assert ComponentSettings.from_environment() == ComponentSettings()


def test_csv_matches_official_scores_and_framework_iterations(
    monkeypatch, tmp_path, evaluation_suite
):
    suite, benchmark, info_calls = evaluation_suite
    for variable in ComponentSettings().environment():
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("DISABLE_DICTIONARY", "YES")
    calls = []

    def experiment(_effect, command, *, timeout, cwd, env):
        assert cwd == suite
        assert timeout == 5.0
        method = command[1]
        calls.append((method, Path(env[MEASUREMENT_ENV])))
        return prediction_experiment(method, env, len(calls))

    monkeypatch.setattr(Effect, "experiment", experiment)
    path = tmp_path / "measurements.csv"
    first = invoke(suite, "--iterations", "2", "--no-static", "--csv", str(path))
    assert first.exit_code == 0, first.output
    assert info_calls == [ComponentSettings(static=False, dictionary=False)]
    assert [method for method, _ in calls] == list(METHODS) * 2
    assert len({path for _, path in calls}) == 4
    (run,) = load_runs(path)
    assert run.complete
    assert run.iterations == 2
    assert run.settings == info_calls[0]
    assert [(row.method, row.iteration) for row in run.measurements] == [
        (method, iteration) for iteration in (1, 2) for method in METHODS
    ]
    assert [row.coverage_percent for row in run.measurements] == [10, 20, 30, 40]
    assert run.measurements[1].observed_outcomes == ("*", "ok")
    assert run.evaluation_elapsed_seconds > 0
    assert run.elapsed_seconds is None

    native_report = run.official["framework_report"]
    summary = jpamb.analyse.Summary.from_sexpr(sexpr.from_string(native_report)[0])
    official_score = summary.score_results(benchmark=benchmark, eff=Effect(None))
    assert official_score.total_score == run.official["total_score"]
    assert official_score.total_abs_time == run.official["total_abs_time_ns"]
    assert official_score.mean_rel_time == run.official["mean_rel_time_db"]
    assert official_score.invalid == run.official["invalid"]
    assert "3 iterations" in official_score.invalid
    assert f"{official_score.total_score:0.2f}" in first.output
    for method in METHODS:
        export_scores = [row.score for row in run.measurements if row.method == method]
        assert run.official["methods"][method]["score"] == sum(export_scores) / 2
    category = run.official["categories"]["category"]
    assert category["hits"] == 0 and category["misses"] == 8

    second = invoke(suite, "--iterations", "1", "--csv", str(path))
    assert second.exit_code == 0, second.output
    first_run, second_run = load_runs(path)
    assert first_run == run
    assert second_run.run_id != run.run_id
    assert second_run.settings == ComponentSettings(dictionary=False)
    header = path.read_text(encoding="utf-8").splitlines()[0]
    assert path.read_text(encoding="utf-8").splitlines().count(header) == 1


def test_timeout_and_protocol_failure_keep_method_iteration_associations(
    monkeypatch, tmp_path, evaluation_suite
):
    suite, _, _ = evaluation_suite
    calls = []

    def experiment(_effect, command, *, env, **kwargs):
        method = command[1]
        calls.append(method)
        if len(calls) == 2:
            raise subprocess.TimeoutExpired(command, timeout=0.1)
        if len(calls) == 3:
            return SimpleNamespace(output="ok;1")
        return prediction_experiment(method, env, len(calls))

    monkeypatch.setattr(Effect, "experiment", experiment)
    path = tmp_path / "measurements.csv"
    result = invoke(suite, "--iterations", "2", "--csv", str(path))
    assert result.exit_code == 1, result.output
    assert "timed out" in result.output
    (run,) = load_runs(path)
    assert run.status == "timeout"
    assert not run.complete
    assert [(row.iteration, row.status) for row in run.measurements] == [
        (1, "success"),
        (1, "timeout"),
        (2, "failed"),
        (2, "success"),
    ]
    assert run.measurements[1].score is None
    assert run.measurements[2].score is None
    assert run.measurements[3].score is not None
    assert run.official["methods"][METHODS[1]]["score"] == run.measurements[3].score


def test_stepwise_checkpoint_is_isolated_by_effective_configuration(
    monkeypatch, tmp_path, evaluation_suite
):
    suite, _, _ = evaluation_suite
    for variable in ComponentSettings().environment():
        monkeypatch.delenv(variable, raising=False)
    calls = []

    def experiment(_effect, command, *, env, **kwargs):
        method = command[1]
        settings = ComponentSettings.from_environment(env)
        calls.append((method, settings))
        if len(calls) == 2:
            raise subprocess.TimeoutExpired(command, timeout=0.1)
        return prediction_experiment(method, env, len(calls))

    monkeypatch.setattr(Effect, "experiment", experiment)
    path = tmp_path / "measurements.csv"
    options = ("--iterations", "1", "--step-wise", "--csv", str(path))
    paused = invoke(suite, *options)
    assert paused.exit_code == 1
    alternate = invoke(suite, *options, "--no-static")
    assert alternate.exit_code == 0, alternate.output
    resumed = invoke(suite, *options)
    assert resumed.exit_code == 0, resumed.output
    enabled = ComponentSettings()
    disabled = ComponentSettings(static=False)
    assert calls == [
        (METHODS[0], enabled),
        (METHODS[1], enabled),
        (METHODS[0], disabled),
        (METHODS[1], disabled),
        (METHODS[1], enabled),
    ]
    failed_run, alternate_run, resumed_run = load_runs(path)
    assert failed_run.status == "timeout"
    assert alternate_run.complete and resumed_run.complete
    assert [row.covered_instructions for row in resumed_run.measurements] == [1, 5]


@pytest.mark.parametrize("companion", [False, True])
def test_report_cannot_overwrite_evaluation_artifacts(
    tmp_path, evaluation_suite, companion
):
    suite, _, info_calls = evaluation_suite
    raw = tmp_path / "measurements.csv"
    report = raw.with_suffix(".runs.jsonl") if companion else raw
    report.write_text("existing data", encoding="utf-8")
    result = invoke(suite, "--csv", str(raw), "--report", str(report))
    assert result.exit_code == 2
    assert "different path" in result.output
    assert report.read_text(encoding="utf-8") == "existing data"
    assert not info_calls
