import jpamb
import jvm
from abstractions import AbstractSmith, Interval

import dynamic_coverage


def test_static_smith_states_seed_dynamic_inputs(monkeypatch):
    method = jvm.AbsMethodID.decode("example.Test.run:(Ljpamb/utils/Smith;)V")
    bc = object()

    def results(bytecode, methodid):
        assert bytecode is bc
        assert methodid == method
        return {
            "assertion error": [AbstractSmith("1?1", Interval(3, 3), Interval(2, 2))],
            "ok": [AbstractSmith.bot()],
        }

    monkeypatch.setattr(dynamic_coverage, "abstract_analysis_results", results)
    monkeypatch.setattr(dynamic_coverage, "generate_inputs_from_dict", lambda *_: [])
    monkeypatch.setattr(dynamic_coverage, "get_method_dictionary", lambda *_: {})
    monkeypatch.setattr(dynamic_coverage, "get_bitstring_structure", lambda *_: [])
    monkeypatch.setattr(dynamic_coverage, "generate_inputs", lambda *_: ["101", "00"])
    monkeypatch.setattr(dynamic_coverage, "fuzz_input", lambda *_: jpamb.case.Input(()))

    seeds = list(dynamic_coverage.analysis_inputs(
        method, None, smith_results=dynamic_coverage.smith_outcomes(bc, method)
    ))
    assert [seed.values[0].value for seed in seeds if seed.values] == ["101", "111", "00"]


def test_guided_mutation_retires_concretely_observed_outcome(monkeypatch):
    method = jvm.AbsMethodID.decode("example.Test.run:(Ljpamb/utils/Smith;)V")
    seed = jpamb.case.Input((jpamb.case.Smith("0000"),))
    results = {
        "ok": [AbstractSmith.from_bits("0000")],
        "assertion error": [AbstractSmith("1?1", Interval(3, 3), Interval(2, 2))],
    }
    observed = []

    def execute(bc, methodid, mutant, max_steps):
        bits = mutant.values[0].value
        observed.append(bits)
        return set(), "assertion error" if bits == "101" else "ok", []

    monkeypatch.setattr(dynamic_coverage, "execute_input", execute)
    monkeypatch.setattr(dynamic_coverage, "mutate_bitstring", lambda *_: "0010")
    behaviors = dynamic_coverage.fuzz_coverage(
        None, method, [seed], {seed}, set(), [], {}, budget=4,
        smith_results=results, known_behaviors={"ok"},
    )
    assert observed == ["101", "0010"]
    assert behaviors == {"ok", "assertion error"}
