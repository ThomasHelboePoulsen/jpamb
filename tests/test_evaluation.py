import csv
import io
import json
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

import jvm
import sexpr
from jpamb.analyse import Category, Config, Response, Result, Summary, Wager
from jpamb.case import Benchmark, Control, Experiment
from jpamb.evaluation import (
    CSV_FIELDS,
    ComponentSettings,
    EvaluationRun,
    MethodMeasurement,
    append_run,
    comparison_report,
    load_runs,
    official_results,
    run_metadata_path,
)
from jpamb.report import AnalysisInfo, Duration
from jpamb.utils import Effect

SMITH = "jpamb.cases.Example.smith:(Ljpamb/utils/Smith;)I"
PLAIN = "jpamb.cases.Example.plain:(I)Ljpamb/utils/Smith;"


def make_run(run_id="test", settings=None):
    measurements = (
        MethodMeasurement(
            SMITH,
            1,
            covered_instructions=10,
            total_instructions=10,
            observed_outcomes=("ok", "out of bounds"),
            analysis_seconds=1,
        ),
        MethodMeasurement(
            PLAIN,
            1,
            covered_instructions=200,
            total_instructions=1000,
            observed_outcomes=(),
            analysis_seconds=2,
        ),
        MethodMeasurement(
            SMITH,
            2,
            covered_instructions=0,
            total_instructions=10,
            observed_outcomes=("ok",),
            analysis_seconds=3,
        ),
        MethodMeasurement(
            PLAIN,
            2,
            covered_instructions=600,
            total_instructions=1000,
            observed_outcomes=("ok",),
            analysis_seconds=4,
        ),
    )
    return EvaluationRun(
        run_id,
        settings or ComponentSettings(),
        iterations=2,
        status="success",
        measurements=measurements,
        official={"total_score": 4},
        expected_methods=(SMITH, PLAIN),
        repetition=1,
        elapsed_seconds=20,
        evaluation_elapsed_seconds=18,
    )


def test_component_settings_isolate_environment_values():
    env = {"DISABLE_STATIC_SEEDS": "yes", "DISABLE_DICTIONARY": "TRUE"}
    settings = ComponentSettings.from_environment(env)
    assert settings == ComponentSettings(static=False, dictionary=False)
    assert ComponentSettings.from_environment({}) == ComponentSettings()
    assert ComponentSettings.from_environment(settings.environment()) == settings
    assert env == {"DISABLE_STATIC_SEEDS": "yes", "DISABLE_DICTIONARY": "TRUE"}


def test_append_preserves_rows_metadata_and_header(tmp_path):
    path = tmp_path / "arbitrary-name.csv"
    first = make_run()
    second = replace(
        make_run("another", ComponentSettings(static=False, dynamic_structure=False)),
        repetition=2,
    )
    append_run(path, first)
    append_run(path, second)
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source)
        assert tuple(reader.fieldnames) == CSV_FIELDS
        rows = list(reader)
    assert len(rows) == 8
    assert rows[0]["method"] == SMITH
    assert rows[0]["coverage_percent"] == "100.0"
    assert json.loads(rows[0]["observed_outcomes"]) == ["ok", "out of bounds"]
    assert rows[1]["observed_outcomes"] == "[]"
    assert rows[3]["iteration"] == "2"
    assert rows[4]["static"] == "false"
    assert rows[4]["dynamic_structure"] == "false"
    assert load_runs(path) == [first, second]
    with pytest.raises(ValueError, match="duplicate run identifier"):
        append_run(path, first)
    assert load_runs(path) == [first, second]


def test_incompatible_schema_and_incomplete_success_rejected(tmp_path):
    path = tmp_path / "old.csv"
    old = "method,covered,total\nm,3,5\n"
    path.write_text(old)
    with pytest.raises(ValueError, match="incompatible evaluation CSV schema"):
        append_run(path, make_run())
    assert path.read_text() == old

    path = tmp_path / "current.csv"
    path.touch()
    assert load_runs(path) == []
    run = make_run()
    append_run(path, run)
    with path.open(encoding="utf-8", newline="") as source:
        rows = list(csv.reader(source))
    with path.open("w", encoding="utf-8", newline="") as output:
        csv.writer(output).writerows(rows[:-1])
    with pytest.raises(ValueError, match="incomplete successful run"):
        load_runs(path)


def test_concurrent_appends_keep_separate_complete_runs(tmp_path):
    path = tmp_path / "shared.csv"
    runs = [make_run(str(index)) for index in range(6)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda run: append_run(path, run), runs))
    assert sorted(load_runs(path), key=lambda run: run.run_id) == runs


def test_statistics_use_runs_as_samples_and_methods_as_equal_weights():
    first = make_run()
    rows = tuple(
        replace(
            row,
            covered_instructions=covered,
            observed_outcomes=("ok", "out of bounds"),
            analysis_seconds=row.analysis_seconds + 2,
        )
        for row, covered in zip(first.measurements, (8, 100, 4, 300))
    )
    second = replace(
        first,
        run_id="independent",
        repetition=2,
        measurements=rows,
        official={"total_score": 6},
        elapsed_seconds=24,
    )
    report = comparison_report([first, second, first], per_method=True)
    assert "| 1 | ON | ON | ON | ON | 5.000 ± 1.414 | 22.000 s ± 2.828 s |" in report
    assert (
        "| 1 | 2 | 0 | 0 | 42.500% ± 3.536 pp | 55.000% ± 7.071 pp | "
        "3.000 ± 1.414 | 7.000 s ± 2.828 s |"
    ) in report
    assert f"| {SMITH} | 55.000% ± 7.071 pp |" in report
    assert f"| {PLAIN} | 30.000% ± 14.142 pp |" in report

    single = comparison_report([first])
    assert "45.000%" in single
    assert "±" not in single


def test_ablation_table_matches_component_columns_and_order():
    runs = [
        make_run("dynamic-off", ComponentSettings(dynamic_structure=False)),
        make_run("all-on"),
        make_run("syntactic-off", ComponentSettings(syntactic_structure=False)),
    ]
    terminal = comparison_report(runs, format="terminal")
    header, separator, *rows = terminal.split("\n\n")[1].splitlines()
    assert [cell.strip() for cell in header.split("|")][:5] == [
        "#",
        "Static",
        "Dict",
        "DynStruct",
        "Syntactic",
    ]
    assert "-+-" in separator
    assert [[cell.strip() for cell in row.split("|")][:5] for row in rows] == [
        ["1", "ON", "ON", "ON", "ON"],
        ["2", "ON", "ON", "ON", "OFF"],
        ["3", "ON", "ON", "OFF", "ON"],
    ]

    html = comparison_report(runs, format="html")
    assert '<th scope="col">DynStruct</th><th scope="col">Syntactic</th>' in html
    assert '<th scope="row">3</th><td>ON</td><td>ON</td><td>OFF</td><td>ON</td>' in html


def test_failed_timeout_and_missing_measurements(tmp_path):
    path = tmp_path / "mixed.csv"
    normal = make_run()
    failed = replace(normal, run_id="bad", status="failed", error="analyzer error")
    timeout = replace(
        normal,
        run_id="slow",
        status="timeout",
        measurements=(MethodMeasurement(SMITH, 1, status="timeout", error="deadline"),),
        official=None,
        error="deadline",
    )
    score_only = replace(
        normal,
        run_id="custom",
        settings=ComponentSettings(dictionary=False),
        measurements=tuple(
            MethodMeasurement(row.method, row.iteration) for row in normal.measurements
        ),
    )
    for run in (failed, timeout, score_only):
        append_run(path, run)
    report = comparison_report(load_runs(path))
    assert "| 1 | ON | ON | ON | ON | — | — | — | — |" in report
    assert "| 2 | ON | OFF | ON | ON | 4.000 |" in report
    assert "| 1 | 0 | 1 | 1 | — | — | — | — | — |" in report
    assert "| 2 | 1 | 0 | 0 | — | — | — | — |" in report
    assert "| bad | 1 | failed | 20.000 s | analyzer error |" in report
    assert "| slow | 1 | timeout | 20.000 s | deadline |" in report


def test_official_score_and_native_results_survive_export(tmp_path):
    a, b = (jvm.AbsMethodID.decode(method) for method in (SMITH, PLAIN))
    benchmark = Benchmark(
        OrderedDict(
            [
                (Experiment(a, None), Control(OrderedDict(), {"ok"})),
                (Experiment(b, None), Control(OrderedDict(), {"null pointer"})),
            ]
        )
    )
    config = Config(
        ("analyzer",),
        AnalysisInfo("tool", "1", "Group", (), "System"),
        OrderedDict([(a, set()), (b, set())]),
        iterations=1,
        timeout=1,
    )
    summary = Summary(
        config,
        {
            a: [
                Result(
                    Response({"ok": Category("mixed"), "divide by zero": Wager(-1)}),
                    Duration(9000, 0.001),
                    (10, 20),
                ),
            ],
            b: [
                Result(
                    Response(
                        {"ok": Category("mixed"), "null pointer": Category("certain")}
                    ),
                    Duration(11000, 0.01),
                    (30, 40),
                ),
            ],
        },
    )
    scored = summary.score_results(benchmark=benchmark, eff=Effect(None))
    official = official_results(benchmark, summary, scored)
    run = EvaluationRun(
        "official",
        ComponentSettings(),
        1,
        "success",
        measurements=(
            MethodMeasurement(SMITH, 1, score=0.5),
            MethodMeasurement(PLAIN, 1, score=1),
        ),
        expected_methods=(SMITH, PLAIN),
        official=official,
    )
    path = tmp_path / "scores.csv"
    append_run(path, run)
    assert load_runs(path) == [run]
    payload = json.loads(run_metadata_path(path).read_text())
    restored = payload["official"]
    assert restored["total_score"] == scored.total_score == 1.5
    assert restored["methods"][SMITH]["score"] == 0.5
    assert restored["methods"][PLAIN]["score"] == 1
    assert (
        restored["invalid"]
        == "Analysis report should be based on 3 iterations, found 1"
    )
    assert restored["categories"]["mixed"]["hits"] == 1
    assert restored["categories"]["mixed"]["misses"] == 1
    assert restored["categories"]["mixed"]["score"] == 0
    assert restored["categories"]["certain"]["wager"] == "inf"
    assert restored["categories"]["certain"]["score"] == "nan"
    assert restored["expected_outcomes"] == {SMITH: ["ok"], PLAIN: ["null pointer"]}
    assert (
        Summary.from_sexpr(sexpr.from_string(restored["framework_report"])[0])
        == summary
    )
    displayed = io.StringIO()
    scored.display(file=displayed)
    assert "     1.50" in displayed.getvalue()
    assert "certain" in displayed.getvalue()
    assert "nan" in displayed.getvalue()
