import csv
from types import SimpleNamespace

import jpamb
import jvm
from jvm.state import PC

import dynamic_coverage


def test_analyse_appends_method_measurements(monkeypatch, tmp_path, capsys):
    method = jvm.AbsMethodID.decode("example.Test.run:(I)V")
    callee = jvm.AbsMethodID.decode("example.Test.helper:()V")
    seed, mutant, second_mutant = [
        jpamb.case.Input((jpamb.case.Int(value),)) for value in range(3)
    ]
    runs = {
        seed: ({PC(method, 0), PC(method, 1), PC(callee, 3)}, "ok"),
        mutant: ({PC(method, 0), PC(method, 2)}, "ok"),
        second_mutant: ({PC(method, 0)}, "assertion error"),
    }
    suite = SimpleNamespace(
        stats_folder=tmp_path / "stats",
        method_opcodes=lambda _method, *, eff: [
            jvm.Return(type=None, offset=offset) for offset in range(4)
        ],
        method_max_locals=lambda _method, *, eff: 1,
    )
    clock = 0.0

    def setup():
        nonlocal clock
        clock += 1
        return suite, None

    def generate_seeds(*_args, **_kwargs):
        nonlocal clock
        clock += 2
        yield seed

    def execute(_bc, _method, inp, max_steps):
        nonlocal clock
        assert max_steps == 2000
        clock += 1
        pcs, outcome = runs[inp]
        return pcs, outcome, []

    write_analysis_csv = dynamic_coverage.write_analysis_csv

    def write_csv(*args, **kwargs):
        nonlocal clock
        clock += 100
        write_analysis_csv(*args, **kwargs)

    export_path = tmp_path / "results" / "metrics.csv"
    monkeypatch.setenv("JPAMB_DYNAMIC_COVERAGE_CSV", str(export_path))
    monkeypatch.setattr(dynamic_coverage, "perf_counter", lambda: clock)
    monkeypatch.setattr(jpamb, "getmethodid", lambda *_args, **_kwargs: method)
    monkeypatch.setattr(jpamb, "setup", setup)
    monkeypatch.setattr(dynamic_coverage, "get_method_dictionary", lambda *_: {})
    monkeypatch.setattr(dynamic_coverage, "get_bitstring_structure", lambda *_: [])
    monkeypatch.setattr(dynamic_coverage, "get_integer_operations", lambda *_: ())
    monkeypatch.setattr(dynamic_coverage, "analysis_inputs", generate_seeds)
    monkeypatch.setattr(dynamic_coverage, "execute_input", execute)
    monkeypatch.setattr(dynamic_coverage, "write_analysis_csv", write_csv)

    for _ in range(2):
        mutations = iter((mutant, second_mutant))
        monkeypatch.setattr(
            dynamic_coverage,
            "mutate_input",
            lambda *_args, **_kwargs: next(mutations, second_mutant),
        )
        dynamic_coverage.analyse()
        predictions = capsys.readouterr().out.splitlines()
        assert len(predictions) == len(jpamb.QUERIES)
        assert "ok;found" in predictions
        assert "assertion error;found" in predictions

    with export_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == [
            "method",
            "covered_instructions",
            "total_instructions",
            "coverage_percent",
            "observed_outcomes",
            "analysis_seconds",
        ]
        rows = list(reader)

    assert len(rows) == 2
    for row in rows:
        assert row["method"] == method.encode()
        assert int(row["covered_instructions"]) == 3
        assert int(row["total_instructions"]) == 4
        assert float(row["coverage_percent"]) == 75
        assert row["observed_outcomes"].split(";") == ["assertion error", "ok"]
        assert float(row["analysis_seconds"]) == 6
