"""Check the static analyser against every Randomness @Case.

The expected outcome must be among the analyser's outcomes, both when the
analyser gets the case's own bitstring and when the bitstring is unknown.
"""

import contextlib
import io
from functools import cache
from pathlib import Path

import pytest

import jpamb
from static import AbstractInterpreter

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
