import jpamb
import jvm
from abstractions import AbstractSmith, Interval

import dynamic_coverage
from helpers import fuzz_context


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

    monkeypatch.setattr(fuzz_context, "abstract_analysis_results", results)
    monkeypatch.setattr(fuzz_context, "generate_bitstring_inputs", lambda *_: ["101", "00"])
    monkeypatch.setattr(fuzz_context, "fuzz_input", lambda *_: jpamb.case.Input(()))

    seeds = list(fuzz_context.analysis_inputs(
        method, None, structure=[("boolean", 0, 0)],
        smith_results=fuzz_context.smith_outcomes(bc, method),
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
    remaining_targets = []
    generate_mutant = dynamic_coverage.generate_mutant

    def execute(bc, methodid, mutant, max_steps, *, record_reads):
        bits = mutant.values[0].value
        observed.append(bits)
        return set(), "assertion error" if bits == "101" else "ok", []

    def generate(ctx, attempts_left, pending_targets):
        remaining_targets.append(set(pending_targets))
        return generate_mutant(ctx, attempts_left, pending_targets)

    monkeypatch.setattr(dynamic_coverage, "execute_input", execute)
    monkeypatch.setattr(dynamic_coverage, "generate_mutant", generate)
    monkeypatch.setattr(dynamic_coverage, "mutate_bitstring", lambda *_: "0010")
    ctx = dynamic_coverage.FuzzContext(
        dictionary={},
        structure=[],
        smith_results=results,
        integer_operations=(),
        initial_seeds=[seed],
        corpus=[seed],
        used_corpus={seed},
        behaviors={"ok"},
    )
    behaviors = dynamic_coverage.coverage_based_fuzzing(None, method, ctx, budget=6)
    assert observed == ["101", "0010"]
    assert remaining_targets == [{"assertion error"}, *[set() for _ in range(5)]]
    assert behaviors == {"ok", "assertion error"}
