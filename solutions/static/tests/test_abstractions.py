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


# --- BitPattern / AbstractSmith (Smith bit-vector abstraction) ---


def st_bitstrings():
    return st.text(alphabet="01", max_size=6)


def st_bitpattern():
    raw = st.builds(
        lambda bits, lo, extra: ab.BitPattern(tuple(bits), ab.Interval(lo, None if extra is None else lo + extra - 1)),
        st.lists(st.sampled_from([0, 1, None]), max_size=6),
        st.integers(min_value=0, max_value=6),
        st.one_of(st.none(), st.integers(min_value=0, max_value=4)),
    )
    return st.one_of(raw, st.sets(st_bitstrings()).map(ab.BitPattern.abstract))


@given(st_bitpattern(), st_bitpattern(), st_bitpattern())
def test_bitpattern_is_poset(a, b, c):
    ab.is_poset(a, b, c)


@given(st_bitpattern(), st_bitpattern(), st_bitpattern())
def test_bitpattern_is_lattice(a, b, c):
    ab.is_lattice(a, b, c)


@given(st.sets(st_bitstrings()), st_bitpattern())
def test_bitpattern_is_galoi(a, b):
    ab.is_galoi(a, b)


@given(st_bitpattern(), st_bitpattern(), st_bitstrings())
def test_bitpattern_join_meet_sound(a, b, s):
    if s in a or s in b:
        assert s in a | b
    # the meet is exact: gamma(a & b) == gamma(a) & gamma(b)
    assert (s in a & b) == (s in a and s in b)


@given(st_bitpattern())
def test_bitpattern_witness_in_gamma(p):
    w = p.witness()
    assert (w is None) == p.is_bot
    if w is not None:
        assert w in p


@given(st_bitstrings(), st.integers(min_value=0, max_value=6), st.integers(min_value=0, max_value=4), st_bitpattern())
def test_smith_draw_sound(s, cursor, count, p):
    """The concrete draw on (s, cursor) is covered by the abstract draw on any abstraction of it."""
    if s not in p:
        return
    smith = ab.AbstractSmith(0, p, ab.Interval(max(cursor - 1, 0), cursor))
    success, exhausted = smith.draw(count)
    if cursor + count > len(s):
        assert exhausted is not None and s in exhausted.pattern
        return
    value = int(s[cursor : cursor + count] or "0", 2)
    assert success is not None
    abs_value, after = success
    assert value in abs_value and s in after.pattern and cursor + count in after.cursor
    if isinstance(abs_value, ab.Drawn):
        # refining with the concrete value keeps s
        assert s in after.pattern.with_slice(abs_value.start, abs_value.width, ab.Interval(value, value))
