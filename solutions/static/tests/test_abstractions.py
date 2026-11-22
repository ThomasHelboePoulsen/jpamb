import abstractions as ab
import pytest
from hypothesis import given
from hypothesis import strategies as st

import jvm
import jvm.state as jvms


def st_i32():
    return st.integers(min_value=-(2**31) - 1, max_value=2**31)


def st_u32():
    return st.integers(min_value=0, max_value=2**32)


def st_stack_ints():
    return st_i32().map(jvms.StackInt)


def st_stack_refs():
    return st_u32().map(jvms.StackReference)


def st_signset():
    return (
        st.sets(st.integers(min_value=-1, max_value=1)).map(frozenset).map(ab.SignSet)
    )


@given(st_signset(), st_signset(), st_signset())
def test_signset_is_poset(a: ab.SignSet, b: ab.SignSet, c: ab.SignSet):
    ab.is_poset(a, b, c)


@given(st_signset(), st_signset(), st_signset())
def test_signset_is_lattice(a: ab.SignSet, b: ab.SignSet, c: ab.SignSet):
    ab.is_lattice(a, b, c)


@given(st.sets(st_stack_ints()), st_signset())
def test_signset_is_galoi(a: set[jvms.StackInt], b: ab.SignSet):
    ab.is_galoi(a, b)


def arithmetic(opr, x, y):
    match opr:
        case jvm.BinaryOpr.Add:
            return jvms.StackInt(x.value + y.value)
        case _:
            raise NotImplementedError("TODO")


@given(
    st.sampled_from([jvm.BinaryOpr.Add]),
    st.sets(st_stack_ints()),
    st.sets(
        st_stack_ints(),
    ),
)
def test_signset_arithmetic(
    opr: jvm.BinaryOpr, xs: set[jvms.StackInt], ys: set[jvms.StackInt]
):
    real = ab.SignSet.abstract(arithmetic(opr, x, y) for x in xs for y in ys)
    (abstracted, _errs) = ab.SignSet.abstract(xs).arithmetic(
        ab.SignSet.abstract(ys), opr
    )
    assert real <= abstracted


def compare(opr, x, y):
    match opr:
        case jvm.CmpOpr.Le:
            return x.value <= y.value
        case _:
            raise NotImplementedError("TODO")


@given(
    st.sampled_from([jvm.CmpOpr.Le]),
    st.sets(st_stack_ints()),
    st.sets(
        st_stack_ints(),
    ),
)
def test_signset_compare(
    opr: jvm.CmpOpr, xs: set[jvms.StackInt], ys: set[jvms.StackInt]
):
    real = {compare(opr, x, y) for x in xs for y in ys}
    abstracted = set(ab.SignSet.abstract(xs).compare(ab.SignSet.abstract(ys), opr))
    assert real <= abstracted


@st.composite
def st_interval(draw):
    if draw(st.booleans()):
        max = None
        if draw(st.booleans()):
            min = None
        else:
            min = draw(st_i32())
    elif draw(st.booleans()):
        min = None
        max = draw(st_i32())

    min, max = sorted([draw(st_i32()), draw(st_i32())])
    return ab.Interval(min, max)



@given(st_interval(), st_interval(), st_interval())
def test_interval_is_poset(a: ab.Interval, b: ab.Interval, c: ab.Interval):
    ab.is_poset(a, b, c)



@given(st_interval(), st_interval(), st_interval())
def test_interval_is_lattice(a: ab.Interval, b: ab.Interval, c: ab.Interval):
    ab.is_lattice(a, b, c)



@given(st.sets(st_stack_ints()), st_interval())
def test_lnterval_is_galoi(a: set[jvms.StackInt], b: ab.Interval):
    ab.is_galoi(a, b)

from hypothesis import given
from hypothesis.strategies import integers, sets

@given(sets(integers()))
def test_interval_abstraction_valid(xs):
  r = ab.Interval.abstract(xs) 
  assert all(x in r for x in xs)

@given(sets(integers()), sets(integers()))
def test_interval_abstraction_distributes(xs, ys):
  assert (ab.Interval.abstract(xs) | ab.Interval.abstract(ys)) == ab.Interval.abstract(xs | ys)

@given(sets(integers()), sets(integers()))
def test_interval_abstraction_add(xs,ys):
  r = ab.Interval.abstract(xs) + ab.Interval.abstract(ys)
  assert all(x + y in r for x in xs for y in ys)

@given(sets(integers()), sets(integers()))
def test_interval_abstraction_sub(xs,ys):
  r = ab.Interval.abstract(xs) - ab.Interval.abstract(ys)
  assert all(x - y in r for x in xs for y in ys)

@given(sets(integers()), sets(integers()))
def test_interval_abstraction_div(xs,ys):
  r = ab.Interval.abstract(xs) / ab.Interval.abstract(ys)
  assert all(x // y in r for x in xs for y in ys if y != 0)


@given(sets(integers()), sets(integers()))
def test_interval_abstraction_mul(xs,ys):
  r = ab.Interval.abstract(xs) * ab.Interval.abstract(ys)
  assert all(x * y in r for x in xs for y in ys)


@given(sets(integers()), sets(integers()))
def test_interval_abstraction_rem(xs,ys):
  r = ab.Interval.abstract(xs) % ab.Interval.abstract(ys)
  assert all(x % y in r for x in xs for y in ys if y != 0)

def st_interval():
    # Lengths and cursors are never negative, so min is always a number >= 0.
    low = st.integers(min_value=0, max_value=6)
    high = st.one_of(st.none(), st.integers(min_value=0, max_value=6))
    return st.tuples(low, high).map(lambda t: ab.Interval(*t))


def st_smith():
    return st.builds(ab.AbstractSmith, st.text("01?", max_size=5), st_interval(), st_interval())


def st_concrete():
    """A concrete smith: (bits, index) with index <= len(bits)."""
    return st.text("01", max_size=6).flatmap(
        lambda bits: st.tuples(st.just(bits), st.integers(min_value=0, max_value=len(bits)))
    )


@given(st_smith(), st_smith(), st_smith())
def test_smith_is_poset(a, b, c):
    ab.is_poset(a, b, c)


@given(st_smith(), st_smith(), st_smith())
def test_smith_is_lattice(a, b, c):
    ab.is_lattice(a, b, c)


@given(st.sets(st_concrete()), st_smith())
def test_smith_is_galoi(a, b):
    ab.is_galoi(a, b)


def concrete_draw(bits: str, index: int, n: int) -> int:
    """What Java BitSmith.draw(n) returns, padding unavailable bits with zero."""
    value = int(bits[index : index + n].ljust(n, "0") or "0", 2)
    return value - 2**32 if value >= 2**31 else value


@given(st_concrete(), st.integers(min_value=0, max_value=32), st_smith())
def test_smith_draw_is_sound(concrete, n, other):
    bits, index = concrete
    smith = ab.AbstractSmith.abstract([concrete]) | other
    value, after = smith.draw(n)
    assert concrete_draw(bits, index, n) in value
    assert (bits, min(index + n, len(bits))) in after


def test_smith_draw_examples():
    smith = ab.AbstractSmith.from_bits("01")
    value, smith = smith.draw(1)
    assert value == ab.Interval(0, 0)
    value, smith = smith.draw(1)
    assert value == ab.Interval(1, 1)
    assert smith.draw(1) == (ab.Interval(0, 0), smith)

    smith = ab.AbstractSmith.from_bits("10")
    value, after = smith.draw(4)
    assert value == ab.Interval(8, 8)
    assert after.cursor == ab.Interval(2, 2)
    assert smith.draw(0) == (ab.Interval(0, 0), smith)

    value, after = ab.AbstractSmith.from_bits("1").draw(32)
    assert value == ab.Interval(-2**31, -2**31)
    assert after.cursor == ab.Interval(1, 1)

    value, after = ab.AbstractSmith.unknown().draw(4)
    assert value == ab.Interval(0, 15)
    assert after.length == ab.Interval(0, None)
    assert after.cursor == ab.Interval(0, 4)