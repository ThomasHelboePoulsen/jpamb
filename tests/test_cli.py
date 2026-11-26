"""
These test, check that the output of the tests remain the same.
"""

import shutil
from collections import OrderedDict
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

import cli
import jpamb
import jvm

analyses = [
    "jpamb-analysis-dummy",
    "basic",
    "syntactic-regex",
    "solution-dynamic-analysis",
]


@pytest.mark.slow
@pytest.mark.parametrize("solution", analyses)
def test_analyse(solution):
    exe = shutil.which(solution)
    if exe is None:
        pytest.skip(f"Could not find {solution} on path")

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "analyse",
            "-f",
            "Simple",
            solution,
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize(
    ("options", "coverage", "outcomes", "timing", "static", "syntactic"),
    [
        ([], "1", "1", "1", "1", "1"),
        (["--no-coverage", "--no-timing"], "0", "1", "0", "1", "1"),
        (["--no-outcomes"], "1", "0", "1", "1", "1"),
        (["--no-static"], "1", "1", "1", "0", "1"),
        (["--no-syntactic"], "1", "1", "1", "1", "0"),
        (["--no-static", "--no-syntactic"], "1", "1", "1", "0", "0"),
    ],
)
def test_analyse_options_apply_to_each_method(
    monkeypatch, tmp_path, options, coverage, outcomes, timing, static, syntactic
):
    monkeypatch.chdir(tmp_path)
    workdir = tmp_path / "suite"
    workdir.mkdir()
    method_ids = ("example.Test.first:()V", "example.Test.second:()V")
    experiments = OrderedDict(
        (
            jpamb.Experiment(jvm.AbsMethodID.decode(method), None),
            jpamb.Control(OrderedDict(), {"ok"}),
        )
        for method in method_ids
    )
    benchmark = jpamb.Benchmark(experiments)
    monkeypatch.setattr(jpamb.Suite, "benchmark", lambda _suite, *, eff: benchmark)

    def info(_effect, command, **kwargs):
        assert command == ("dynamic-coverage-analysis", "info")
        return "dynamic\n1.0\nBit Diddlers\ndynamic,python\n"

    calls = []
    predictions = "\n".join(
        f"{query};{6 if query == 'ok' else -6}" for query in jpamb.QUERIES
    )

    def experiment(_effect, command, *, timeout, cwd, env):
        assert command[0] == "dynamic-coverage-analysis"
        calls.append(command[1])
        assert cwd == workdir
        assert env["JPAMB_DYNAMIC_COVERAGE_CSV"] == str(tmp_path / "metrics.csv")
        assert env["JPAMB_DYNAMIC_COVERAGE"] == coverage
        assert env["JPAMB_DYNAMIC_OUTCOMES"] == outcomes
        assert env["JPAMB_DYNAMIC_TIMING"] == timing
        assert env["JPAMB_DYNAMIC_STATIC"] == static
        assert env["JPAMB_DYNAMIC_SYNTACTIC"] == syntactic
        return SimpleNamespace(
            output=predictions,
            time_ns=1_000_000,
            time_relative=0.0,
            calibrations_ns=[1_000_000],
        )

    monkeypatch.setattr(cli.Effect, "run", info)
    monkeypatch.setattr(cli.Effect, "experiment", experiment)
    result = CliRunner().invoke(
        cli.cli,
        [
            "--workdir",
            str(workdir),
            "analyse",
            "--iterations",
            "1",
            "--csv",
            "metrics.csv",
            *options,
            "dynamic-coverage-analysis",
        ],
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert calls == list(method_ids)


@pytest.mark.slow
def test_analyse_report(tmp_path):
    runner = CliRunner()

    solution = "jpamb-analysis-dummy"
    exe = shutil.which(solution)
    if exe is None:
        pytest.skip(f"Could not find {solution} on path")

    result = runner.invoke(
        cli.cli,
        [
            "-vv",
            "analyse",
            "--report",
            (tmp_path / "report.sexp"),
            exe,
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output


@pytest.mark.slow
def test_checkhealth(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "checkhealth",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output


interpreters = [
    "solution-dynamic-interpreter",
]


@pytest.mark.slow
@pytest.mark.parametrize("solution", interpreters)
def test_interpret(tmp_path, solution):
    exe = shutil.which(solution)
    if exe is None:
        pytest.skip(f"Could not find {solution} on path")

    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        [
            "interpret",
            "--report",
            (tmp_path / "report.sexp"),
            solution,
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output


methods = [
    "jpamb.cases.Simple.assertBoolean:(Z)V",
]

formats = ["pretty", "real", "repr", "json"]


@pytest.mark.slow
@pytest.mark.parametrize("method", methods)
@pytest.mark.parametrize("format", formats)
def test_inspect(method, format):
    runner = CliRunner()
    result = runner.invoke(
        cli.cli,
        ["-v", "inspect", "--format", format, method],
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output


# @pytest.mark.slow
# @pytest.mark.parametrize("format", ["autolab", "user"])
# def test_validate_analysis(format):
#     runner = CliRunner()
#     result = runner.invoke(
#         cli.cli,
#         [
#             "-v",
#             "validate",
#             "analyse",
#             "--format",
#             format,
#             "tests/data/analysis-report.sexp",
#         ],
#         catch_exceptions=False,
#     )
#
#     assert result.exit_code == 0, result.output
#
#
# @pytest.mark.slow
# @pytest.mark.parametrize("format", ["autolab", "user"])
# def test_validate_interpret(format):
#     runner = CliRunner()
#     result = runner.invoke(
#         cli.cli,
#         [
#             "-v",
#             "validate",
#             "interpret",
#             "--format",
#             format,
#             "tests/data/interpret-report.sexp",
#         ],
#         catch_exceptions=False,
#     )
#
#     assert result.exit_code == 0, result.output
