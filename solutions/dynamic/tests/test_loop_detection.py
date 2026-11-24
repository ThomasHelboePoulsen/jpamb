from pathlib import Path

import pytest

import jpamb
from dynamic_coverage import execute_input


@pytest.mark.parametrize(
    "method, argument, expected",
    [
        ("Randomness.loopUntilHeads:(Ljpamb/utils/Smith;)V", jpamb.case.Smith("0000"), "*"),
        ("Randomness.loopUntilHeads:(Ljpamb/utils/Smith;)V", jpamb.case.Smith("0001"), "ok"),
        ("Randomness.loopUntilHeads:(Ljpamb/utils/Smith;)V", jpamb.case.Smith("00001"), "assertion error"),
        ("Dependent.divisionLoop:(I)V", jpamb.case.Int(0), "ok"),
        ("Dependent.divisionLoop:(I)V", jpamb.case.Int(1024), "assertion error"),
    ],
)
def test_loop_detection(method, argument, expected):
    suite = jpamb.Suite.from_workdir(Path(__file__).resolve().parents[3])
    bc = jpamb.Bytecode(suite, jpamb.Effect(None), {})
    methodid = jpamb.parse_methodid(f"jpamb.cases.{method}")

    _, behavior, _ = execute_input(bc, methodid, jpamb.case.Input((argument,)))

    assert behavior == expected
