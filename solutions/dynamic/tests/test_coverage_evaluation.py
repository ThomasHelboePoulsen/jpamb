import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import dynamic_coverage
import pytest
from abstractions import AbstractSmith
from helpers import fuzz_context

import jpamb
import jvm
from jpamb.evaluation import MEASUREMENT_ENV, ComponentSettings
from jvm.state import PC

METHOD = jvm.AbsMethodID.decode("example.Test.run:(Ljpamb/utils/Smith;)V")


@pytest.fixture(autouse=True)
def enabled_components(monkeypatch):
    for name in ComponentSettings().environment():
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    "disabled",
    [
        "DISABLE_STATIC_SEEDS",
        "DISABLE_DICTIONARY",
        "DISABLE_SYNTACTIC_STRUCTURE",
        "DISABLE_DYNAMIC_STRUCTURE",
    ],
)
def test_component_controls_disable_guidance_and_are_isolated(monkeypatch, disabled):
    monkeypatch.setenv(disabled, "YeS")
    operations = Mock(return_value=(object(),))
    dictionary = Mock(return_value={int: [5]})
    structure = Mock(return_value=[("boolean", 0, 0)])
    static = Mock(return_value={"ok": [AbstractSmith.from_bits("1")]})
    inputs = Mock(return_value=[jpamb.case.Input(())])
    monkeypatch.setattr(fuzz_context, "get_integer_operations", operations)
    monkeypatch.setattr(fuzz_context, "get_method_dictionary", dictionary)
    monkeypatch.setattr(fuzz_context, "get_bitstring_structure", structure)
    monkeypatch.setattr(fuzz_context, "smith_outcomes", static)
    monkeypatch.setattr(fuzz_context, "analysis_inputs", inputs)

    context = fuzz_context.init_context(METHOD, None, None)
    assert operations.called == dictionary.called == (disabled != "DISABLE_DICTIONARY")
    assert structure.called == (disabled != "DISABLE_SYNTACTIC_STRUCTURE")
    assert static.called == (disabled != "DISABLE_STATIC_SEEDS")
    assert context.use_dynamic_structure == (disabled != "DISABLE_DYNAMIC_STRUCTURE")
    assert (
        bool(context.integer_operations)
        == bool(context.dictionary)
        == dictionary.called
    )
    assert bool(context.structure) == structure.called
    assert bool(dynamic_coverage.init_pending_targets(context)) == static.called
    inputs.assert_called_once_with(
        METHOD,
        None,
        context.structure,
        context.dictionary,
        context.smith_results,
        context.integer_operations,
    )

    monkeypatch.delenv(disabled)
    enabled = fuzz_context.init_context(METHOD, None, None)
    assert enabled.dictionary and enabled.integer_operations and enabled.structure
    assert enabled.smith_results and enabled.use_dynamic_structure
    assert context.use_dynamic_structure == (disabled != "DISABLE_DYNAMIC_STRUCTURE")


@pytest.mark.parametrize("use_dynamic_structure", [True, False])
def test_dynamic_discovery_keeps_interpretation_and_fuzzing_active(
    monkeypatch, use_dynamic_structure
):
    initial_input = jpamb.case.Input((jpamb.case.Smith("0"),))
    mutant = jpamb.case.Input((jpamb.case.Smith("1"),))
    context = fuzz_context.FuzzContext(
        dictionary={},
        structure=[],
        smith_results={},
        integer_operations=(),
        initial_seeds=[initial_input],
        use_dynamic_structure=use_dynamic_structure,
    )
    discoveries = Mock()
    monkeypatch.setattr(dynamic_coverage, "queue_dynamic_field_inputs", discoveries)
    monkeypatch.setattr(dynamic_coverage, "generate_mutant", lambda *_: mutant)
    monkeypatch.setattr(
        dynamic_coverage, "initial", lambda _, __, inp: SimpleNamespace(inp=inp)
    )
    recorded = []

    def step(_, state):
        offset = int(state.inp.values[0].value)
        reads = getattr(state, "recorded_reads", None)
        recorded.append(reads is not None)
        if reads is not None:
            reads.append(("boolean", offset, offset))
        return PC(METHOD, offset), ("ok", "assertion error")[offset]

    monkeypatch.setattr(dynamic_coverage, "step", step)
    dynamic_coverage.run_initial_seeds(None, METHOD, context)
    outcomes = dynamic_coverage.coverage_based_fuzzing(None, METHOD, context, budget=1)

    assert recorded == [use_dynamic_structure, use_dynamic_structure]
    assert outcomes == {"ok", "assertion error"}
    assert context.pc_coverage == {PC(METHOD, 0), PC(METHOD, 1)}
    assert context.corpus == [initial_input, mutant]
    if use_dynamic_structure:
        assert context.structure == [("boolean", 0, 0), ("boolean", 1, 1)]
        assert [call.args[1:] for call in discoveries.call_args_list] == [
            (initial_input, [("boolean", 0, 0)]),
            (mutant, [("boolean", 1, 1)]),
        ]
    else:
        assert context.structure == []
        discoveries.assert_not_called()


@pytest.mark.parametrize("measure", [True, False])
def test_analyser_measurements_preserve_prediction_protocol(
    monkeypatch, tmp_path, capsys, measure
):
    path = tmp_path / "measure.json"
    monkeypatch.delenv(MEASUREMENT_ENV, raising=False)
    if measure:
        monkeypatch.setenv(MEASUREMENT_ENV, str(path))
    monkeypatch.setenv("DISABLE_DICTIONARY", "1")
    monkeypatch.setattr(sys, "argv", ["dynamic-coverage-analysis", METHOD.encode()])
    callee = jvm.AbsMethodID.decode("example.Test.callee:()V")
    context = SimpleNamespace(
        pc_coverage={PC(METHOD, 0), PC(METHOD, 0), PC(METHOD, 2), PC(callee, 1)},
        behaviors={"ok", "*", "extra outcome"},
    )
    events = []
    times = iter((12.0, 15.0))

    def clock():
        events.append("clock")
        return next(times)

    def setup():
        events.append("setup")
        return None, None

    class Bytecode:
        def __init__(self, *_):
            events.append("bytecode")

        def getmethod(self, method):
            assert method == METHOD
            events.append("opcodes")
            return SimpleNamespace(opcodes=[None] * 4)

    def init(*_, settings):
        events.append("inputs")
        assert settings == ComponentSettings(dictionary=False)
        return context

    monkeypatch.setattr(dynamic_coverage, "perf_counter", clock)
    monkeypatch.setattr(jpamb, "setup", setup)
    monkeypatch.setattr(jpamb, "Bytecode", Bytecode)
    monkeypatch.setattr(dynamic_coverage, "init_context", init)
    monkeypatch.setattr(
        dynamic_coverage, "run_initial_seeds", lambda *_, **__: events.append("seeds")
    )
    monkeypatch.setattr(
        dynamic_coverage,
        "coverage_based_fuzzing",
        lambda *_, **__: events.append("fuzz"),
    )

    dynamic_coverage.analyse()

    predictions = {"ok": "found", "*": "timeout"}
    assert capsys.readouterr().out == "".join(
        f"{query};{predictions.get(query, 'not-found')}\n" for query in jpamb.QUERIES
    )
    analysis_events = ["setup", "bytecode", "inputs", "seeds", "fuzz"]
    if measure:
        assert events == ["clock", *analysis_events, "opcodes", "clock"]
        assert json.loads(path.read_text(encoding="utf-8")) == {
            "method": METHOD.encode(),
            "configuration": {
                "static": True,
                "dictionary": False,
                "syntactic_structure": True,
                "dynamic_structure": True,
            },
            "has_smith": True,
            "covered_instructions": 2,
            "total_instructions": 4,
            "coverage_percent": 50.0,
            "observed_outcomes": ["*", "extra outcome", "ok"],
            "analysis_seconds": 3.0,
        }
    else:
        assert events == analysis_events
        assert not path.exists()
