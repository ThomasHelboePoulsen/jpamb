"""Check the static analyser against every Randomness @Case.

The expected outcome must be among the analyser's outcomes, both when the
analyser gets the case's own bitstring and when the bitstring is unknown.
"""

import contextlib
import io
from functools import cache
from pathlib import Path
from types import SimpleNamespace

import pytest

import jpamb
import jvm
from jvm.state import PC
from abstractions import Interval
from static import AbstractInterpreter, abstract_analysis_results, answer

ROOT = Path(__file__).resolve().parents[3]
SUITE = jpamb.Suite.from_workdir(ROOT)
EFF = jpamb.Effect(None)
BC = jpamb.Bytecode(SUITE, EFF, {})
CASES = [c for c in SUITE.cases(eff=EFF) if "Randomness" in str(c.experiment.entry)]


def outcomes(mid, inp, steps=1000) -> set[str]:
    ai = AbstractInterpreter.initial(BC, mid, inp)
    finals = set()
    with contextlib.redirect_stderr(io.StringIO()):
        while steps and ai.worklist:
            finals |= ai.step()[1]
            steps -= 1
    if ai.worklist:  # ran out of budget: may loop forever
        finals.add("*")
    return finals


@pytest.fixture(autouse=True)
def run_from_repo_root(monkeypatch):
    # the analyser finds source files relative to the working directory
    monkeypatch.chdir(ROOT)


@cache
def outcomes_unknown_bits(mid) -> frozenset[str]:
    return frozenset(outcomes(mid, None))


@pytest.mark.parametrize("case", CASES, ids=str)
def test_randomness_case(case):
    mid, inp, expected = case.experiment.entry, case.experiment.input, case.result
    exact = outcomes(mid, inp)
    unknown = outcomes_unknown_bits(mid)
    # Smith never throws: missing bits read as 0
    assert "illegal state" not in exact | unknown
    if expected != "*":
        assert expected in exact, f"exact input gave {sorted(exact)}"
        assert expected in unknown, f"unknown input gave {sorted(unknown)}"


def test_branches_teach_the_smith_its_bits():
    """twoDraws asserts !(first && second): with an unknown bitstring, the
    analyser should learn that the assertion error needs bits 11."""
    mid = next(c.experiment.entry for c in CASES if c.experiment.entry.extension.name == "twoDraws")
    ai = AbstractInterpreter.initial(BC, mid, None)
    with contextlib.redirect_stderr(io.StringIO()):
        while ai.worklist:
            ai.step()
    [pc] = [pc for pc in ai.states if pc.method == mid and "AssertionError" in str(BC[pc])]
    assert ai.states[pc].smith.pattern == "11"


def test_abstract_analysis_results():
    mid = next(c.experiment.entry for c in CASES if c.experiment.entry.extension.name == "twoDraws")
    outcomes = abstract_analysis_results(BC, mid)
    assert set(outcomes) == {"ok", "assertion error"}
    [error] = outcomes["assertion error"]
    assert error.pattern == "11" and error.length == Interval(2, None)
    [ok] = outcomes["ok"]
    assert ok.pattern == ""


@pytest.mark.parametrize(
    "method, expected",
    [
        ("Loops.forever", "yes"),  # no outcome reachable at all
        ("Loops.neverAsserts", "yes"),
        ("Randomness.loopUntilHeads", "maybe"),  # loop that can run forever
        ("Randomness.spinOnTails", "maybe"),
        ("Randomness.twoDraws", "no"),  # no loop: always stops
    ],
)
def test_star_answer(method, expected):
    mid = next(c.experiment.entry for c in SUITE.cases(eff=EFF) if f"cases.{method}:" in str(c.experiment.entry))
    assert answer("*", abstract_analysis_results(BC, mid)) == expected


def test_loop_heads_are_in_the_results():
    mid = next(c.experiment.entry for c in CASES if c.experiment.entry.extension.name == "loopUntilHeads")
    results = abstract_analysis_results(BC, mid)
    assert len(results["*"]) == 1  # one loop
    assert "*" not in abstract_analysis_results(BC, next(
        c.experiment.entry for c in CASES if c.experiment.entry.extension.name == "twoDraws"))


def test_mutual_recursion_widens_smith_cursor(monkeypatch):
    first = jvm.AbsMethodID.decode("example.Test.first:(Ljpamb/utils/Smith;)V")
    second = jvm.AbsMethodID.decode("example.Test.second:(Ljpamb/utils/Smith;)V")
    draw = jvm.AbsMethodID.decode("jpamb.utils.Smith.draw:()Z")
    bytecode = {
        PC(method, opcode.offset): opcode
        for method, callee in ((first, second), (second, first))
        for opcode in (
            jvm.Load(jvm.Reference(), 0, offset=0),
            jvm.InvokeInterface(draw, 1, offset=1),
            jvm.Store(jvm.Int(), 1, offset=2),
            jvm.Load(jvm.Reference(), 0, offset=3),
            jvm.InvokeStatic(callee, offset=4),
            jvm.Return(None, offset=5),
        )
    }

    class TestBytecode(dict):
        suite = None

        def getmethod(self, method):
            return SimpleNamespace(max_locals=2)

    monkeypatch.setattr("static.get_literals_in_method", lambda *_: {})
    ai = AbstractInterpreter.initial(TestBytecode(bytecode), first, None)
    for _ in range(100):
        if not ai.worklist:
            break
        ai.step(trace=False)

    assert not ai.worklist
    assert ai.outcome_smiths["*"][PC(first, 0)].cursor == Interval(0, None)
