import pytest

import dynamic_coverage
import jpamb
import jvm
from abstractions import AbstractSmith
from jvm.state import PC


@pytest.mark.parametrize("static_enabled", [True, False])
@pytest.mark.parametrize("syntactic_enabled", [True, False])
def test_dynamic_guidance_options(monkeypatch, capsys, static_enabled, syntactic_enabled):
    method = jvm.AbsMethodID.decode("example.Test.run:(Ljpamb/utils/Smith;I)V")
    static_bits = "110010101011"
    literal_bits = "111000100101"
    random_bits = "101010111001"
    mutant_bits = "101100100111"
    static_target = AbstractSmith.from_bits(static_bits)
    literal_dictionary = {int: [42]}
    source_field = ("integer", 0, 31)
    runtime_field = ("boolean", 12, 12)
    integer_operations = (("+", 42),)
    extracted_guidance = []
    executed_bits = set()
    mutations = []

    def make_input(bits):
        return jpamb.case.Input((jpamb.case.Smith(bits), jpamb.case.Int(0)))

    def static_results(_bc, _method):
        extracted_guidance.append("static")
        return {"assertion error": [static_target]}

    def get_dictionary(_method, _suite):
        extracted_guidance.append("dictionary")
        return literal_dictionary

    def dictionary_seeds(_method, _suite):
        extracted_guidance.append("dictionary seeds")
        yield make_input(literal_bits)

    def bitstring_structure(_method, _suite):
        extracted_guidance.append("structure")
        return [source_field]

    def get_integer_operations(_method, _suite):
        extracted_guidance.append("operations")
        return integer_operations

    def execute_input(_bc, _method, inp, max_steps):
        assert max_steps == 2000
        bits = inp.values[0].value
        executed_bits.add(bits)
        if bits == mutant_bits:
            return {PC(method, 1)}, "assertion error", []
        return {PC(method, 0)}, "ok", [runtime_field]

    def mutate_input(_seed, structure, dictionary, *, target, integer_operations):
        mutations.append((tuple(structure), dictionary, target, integer_operations))
        return make_input(mutant_bits)

    for name, enabled in (
        ("JPAMB_DYNAMIC_STATIC", static_enabled),
        ("JPAMB_DYNAMIC_SYNTACTIC", syntactic_enabled),
    ):
        if enabled:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, "0")
    monkeypatch.setenv("JPAMB_DYNAMIC_COVERAGE_CSV", "")
    monkeypatch.setattr(jpamb, "getmethodid", lambda *_args, **_kwargs: method)
    monkeypatch.setattr(jpamb, "setup", lambda: (None, None))
    monkeypatch.setattr(dynamic_coverage, "smith_outcomes", static_results)
    monkeypatch.setattr(dynamic_coverage, "get_method_dictionary", get_dictionary)
    monkeypatch.setattr(dynamic_coverage, "generate_inputs_from_dict", dictionary_seeds)
    monkeypatch.setattr(dynamic_coverage, "get_bitstring_structure", bitstring_structure)
    monkeypatch.setattr(dynamic_coverage, "get_integer_operations", get_integer_operations)
    monkeypatch.setattr(dynamic_coverage, "fuzz_input", lambda *_args: make_input(random_bits))
    monkeypatch.setattr(dynamic_coverage, "execute_input", execute_input)
    monkeypatch.setattr(dynamic_coverage, "mutate_input", mutate_input)

    dynamic_coverage.analyse()

    expected_guidance = {"static"} if static_enabled else set()
    if syntactic_enabled:
        expected_guidance.update(("dictionary", "dictionary seeds", "structure", "operations"))
    assert set(extracted_guidance) == expected_guidance
    assert (static_bits in executed_bits) == static_enabled
    assert (literal_bits in executed_bits) == syntactic_enabled
    assert {"", random_bits, mutant_bits} <= executed_bits

    fields, dictionary, target, operations = mutations[0]
    assert fields == ((source_field, runtime_field) if syntactic_enabled else (runtime_field,))
    assert dictionary == (literal_dictionary if syntactic_enabled else {})
    assert target is (static_target if static_enabled else None)
    assert operations == (integer_operations if syntactic_enabled else ())
    predictions = capsys.readouterr().out.splitlines()
    assert "ok;found" in predictions
    assert "assertion error;found" in predictions
