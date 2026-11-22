from pathlib import Path
import pytest

import jpamb
from jpamb.utils import Effect
import jvm
from bitstring_structure import get_bitstring_fields, get_bitstring_structure


@pytest.fixture(scope="module")
def suite():
    
    return jpamb.Suite.from_workdir(Path.cwd())


def find_method_id(suite: jpamb.Suite, method_name: str) -> jvm.AbsMethodID:
    eff = Effect(None)
    try:
        for case in suite.cases(eff=eff):
            if case.methodid.extension.name == method_name:
                return case.methodid
    except Exception:
        pass
    # Fallback to direct method id if cases.txt is not yet rebuilt
    return jvm.AbsMethodID.decode(f"jpamb.cases.Randomness.{method_name}:(Ljpamb/utils/Smith;)V")


def test_draw_int(suite):
    
    methodid = find_method_id(suite, "drawInt")
    structure = get_bitstring_structure(methodid, suite)

    # The two 32-bit reads start at different offsets on each branch.
    assert structure == [
        ("integer", 0, 3),
        ("integer", 4, 13),
        ("integer", 4, 35),
        ("integer", 14, 45),
        ("integer", 36, 67),
        ("integer", 46, 77),
    ]


def test_compare_ints(suite):
    methodid = find_method_id(suite, "compareInts")
    assert get_bitstring_structure(methodid, suite) == [
        ("integer", 0, 31),
        ("integer", 32, 63),
    ]


def test_draw_in_callee(suite):
    
    methodid = find_method_id(suite, "drawInCallee")
    structure = get_bitstring_structure(methodid, suite)

  
    assert structure == [
        ("boolean", 0, 0),
    ]


def test_spin_on_tails(suite):
    methodid = find_method_id(suite, "spinOnTails")
    structure = get_bitstring_structure(methodid, suite)

    assert structure == [
        ("boolean", 0, 0),
    ]


def test_branch_overlap(suite):
    # has overlaops in values in places.
    methodid = find_method_id(suite, "branchOverlap")
    structure = get_bitstring_structure(methodid, suite)

    
    assert structure == [
        ("integer", 0, 3),
        ("boolean", 4, 4), # value>= 5 not taken.
        ("integer", 4, 13), 
        ("boolean", 14, 14), #value>=5 taken.
    ]


def test_static_draw_width_guides_coverage(tmp_path, monkeypatch):
    from dynamic_coverage import get_analysis_structure

    monkeypatch.chdir(tmp_path)
    source = tmp_path / "cases" / "WidthExample.java"
    source.parent.mkdir()
    source.write_text(
        "class WidthExample { static int run(Smith smith) { return smith.draw(2 + 2); } }",
        encoding="utf-8",
    )
    suite = jpamb.Suite.from_workdir(tmp_path)
    methodid = jvm.AbsMethodID.decode("WidthExample.run:(Ljpamb/utils/Smith;)I")
    draw = jvm.AbsMethodID.decode("jpamb.utils.Smith.draw:(I)I")
    opcodes = [
        jvm.Load(type=jvm.Reference(), index=0, offset=0),
        jvm.Push(type=jvm.Int(), value=4, offset=1),
        jvm.InvokeInterface(method=draw, stack_size=2, offset=2),
        jvm.Return(type=jvm.Int(), offset=3),
    ]
    bc = jpamb.Bytecode(suite, Effect(None), {methodid: jvm.Method(methodid, opcodes, 1)})

    assert get_bitstring_structure(methodid, suite) == [("integer", 0, 31)]
    assert get_analysis_structure(bc, methodid) == [("integer", 0, 3), ("integer", 0, 31)]


if __name__ == "__main__":
    current_suite = jpamb.Suite.from_workdir(Path.cwd())
    eff = Effect(None)
    for name in ["drawInt", "drawInCallee", "spinOnTails", "branchOverlap"]:
        mid = find_method_id(current_suite, name)
        tuples = get_bitstring_structure(mid, current_suite)
        fields = get_bitstring_fields(mid, current_suite)
        print(f"=== {name} ===")
        print(f"Structure: {tuples}")
        for f in fields:
            print(f"  {f.field_type}: bits [{f.start_index}..{f.end_index}]")
        print()
