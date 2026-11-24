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


def bitwise(opr, x, y):
    if opr == jvm.BitOpr.Shl:
        result = (x << (y & 0b11111)) & 0xFFFFFFFF
        return result if result < 2**31 else result - 2**32
    if opr == jvm.BitOpr.Shr:
        return x >> (y & 0b11111)
    if opr == jvm.BitOpr.Ushr:
        result = (x & 0xFFFFFFFF) >> (y & 0b11111)
        return result if result < 2**31 else result - 2**32
    if opr == jvm.BitOpr.And:
        return x & y
    if opr == jvm.BitOpr.Or:
        return x | y
    if opr == jvm.BitOpr.Xor:
        return x ^ y
    raise NotImplementedError(opr)


@given(
    st.sampled_from(list(jvm.BitOpr)),
    st.sets(st.integers(min_value=-100, max_value=100)),
    st.sets(st.integers(min_value=-100, max_value=100)),
)
def test_interval_bitwise_is_sound(opr, xs, ys):
    if not xs or not ys:
        return
    real = {bitwise(opr, x, y) for x in xs for y in ys}
    abstracted = ab.Interval.abstract(xs).bitwise(ab.Interval.abstract(ys), opr)
    assert all(result in abstracted for result in real)

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
    padded = bits[index : index + n].ljust(n, "0")
    value = int(padded[-32:] or "0", 2)
    return value - 2**32 if value >= 2**31 else value


@given(st_concrete(), st.integers(min_value=0, max_value=40), st_smith())
def test_smith_draw_is_sound(concrete, n, other):
    bits, index = concrete
    smith = ab.AbstractSmith.abstract([concrete]) | other
    result, after = smith.draw(n)
    assert concrete_draw(bits, index, n) in result
    assert (bits, min(index + n, len(bits))) in after


def test_smith_draw_examples():
    smith = ab.AbstractSmith.from_bits("01")
    value, smith = smith.draw(1)
    assert value == ab.Interval(0, 0)
    value, smith = smith.draw(1)
    assert value == ab.Interval(1, 1)
    value, after = smith.draw(1)  # past the end: 0; the real index stays at min(3, 2) = 2
    assert value == ab.Interval(0, 0)
    assert after.cursor == ab.Interval(3, 3) and ("01", 2) in after

    value, after = ab.AbstractSmith.unknown().draw(4)
    assert value == ab.Interval(0, 15)
    assert after.length == ab.Interval(0, None)
    assert after.cursor == ab.Interval(4, 4)  # stays exact, even if the string is shorter

    smith = ab.AbstractSmith.from_bits("1" + "0" * 32 + "11")
    value, after = smith.draw(34)
    assert value == ab.Interval(1, 1)
    assert ("1" + "0" * 32 + "11", 34) in after


@given(st_concrete(), st.integers(min_value=0, max_value=6), st_smith(), st_i32(), st_i32())
def test_smith_learn_is_sound(concrete, n, other, a, b):
    """Learning any range that holds the real value never loses the real bitstring."""
    bits, index = concrete
    smith = ab.AbstractSmith.abstract([concrete]) | other
    value = concrete_draw(bits, index, n)
    result, after = smith.draw(n)
    if not isinstance(result, ab.Drawn):
        return
    lo, hi = sorted([a, b])
    for narrowed in (ab.Interval(value, value), ab.Interval(min(lo, value), max(hi, value))):
        learned = after.learn(result.start, result.width, narrowed)
        assert (bits, min(index + n, len(bits))) in learned


def test_smith_draw_count_interval_includes_intermediate_signed_value():
    bits = "1" + "0" * 32
    smith = ab.AbstractSmith.from_bits(bits)
    value, after = smith.draw_counts(ab.Interval(31, 33))

    for count in (31, 32, 33):
        assert concrete_draw(bits, 0, count) in value
        assert (bits, count) in after


def test_smith_learn_examples():
    # draw() is 1 on the true branch: that bit is 1 and the string is that long
    value, smith = ab.AbstractSmith.unknown().draw(1)
    learned = smith.learn(value.start, value.width, ab.Interval(1, 1))
    assert learned.pattern == "1" and learned.length == ab.Interval(1, None)

    # draw(4) >= 8: only the top bit is shared by 8..15
    value, smith = ab.AbstractSmith.unknown().draw(4)
    assert smith.learn(value.start, value.width, ab.Interval(8, 15)).pattern == "1"

    # input "1", bit 1 read as 0: that 0 is padding, the string stays "1"
    _, smith = ab.AbstractSmith.from_bits("1").draw(1)
    value, smith = smith.draw(1)
    assert smith.learn(value.start, value.width, ab.Interval(0, 0)) == smith
