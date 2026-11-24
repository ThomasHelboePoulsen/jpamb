from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal, Self
from unittest import result

import jvm
import jvm.state as jvms


class Poset(ABC):
    @abstractmethod
    def __eq__(self, other: Self) -> bool: ...

    @abstractmethod
    def __lt__(self, other: Self) -> bool: ...

    def __le__(self, other: Self) -> bool:
        return self == other or self < other

    @abstractmethod
    def __gt__(self, other: Self) -> bool: ...

    def __ge__(self, other: Self) -> bool:
        return self == other or self > other


def is_reflexive(a: Poset):
    # Checking if the relation is reflexive (a == a)
    assert a == a, f"Reflexivity check failed: Element {a} is not related to itself."  # noqa: PLR0124


def is_antisymmetric(a: Poset, b: Poset):
    if a != b:
        # Checking that if a <= b and b <= a, then a must equal b
        assert not (a <= b <= a), (
            f"Antisymmetry violation: Found elements where {a} <= {b} and {b} <= {a}, "
            f"but {a} != {b}."
        )


def is_transitive(a: Poset, b: Poset, c: Poset):
    if a <= b <= c:
        # Checking that if a <= b and b <= c, then a <= c
        assert a <= c, (
            f"Transitivity violation: Found path {a} <= {b} and {b} <= {c}, "
            f"but {a} is not related to {c}."
        )


def is_poset(a: Poset, b: Poset, c: Poset):
    for x in [a, b, c]:
        is_reflexive(x)

    for x in [b, c]:
        is_antisymmetric(a, x)

    is_transitive(a, b, c)


class Lattice(Poset):
    @classmethod
    @abstractmethod
    def top(cls) -> Self:
        raise NotImplementedError(f"top: {cls}")

    @classmethod
    def bot(cls) -> Self:
        return cls.abstract([])

    @abstractmethod
    def __or__(self, other: Self) -> Self: ...

    @abstractmethod
    def __and__(self, other: Self) -> Self: ...


def is_lattice_identities(a: Lattice):
    # Top element identity checks
    assert (a | a.top()) == a.top(), (
        f"Top identity fail: ({a} | {a.top()}) -> {a | a.top()} != {a.top()}"
    )
    assert (a.top() | a) == a.top(), (
        f"Top identity fail (commute): ({a.top()} | {a}) != {a.top()}"
    )
    assert (a & a.top()) == a, f"Top identity fail (meet): ({a} & {a.top()}) != {a}"
    assert (a.top() & a) == a, (
        f"Top identity fail (meet commute): ({a.top()} & {a}) != {a}"
    )

    # Bottom element identity checks
    assert (a & a.bot()) == a.bot(), (
        f"Bottom identity fail: ({a} & {a.bot()}) != {a.bot()}"
    )
    assert (a.bot() & a) == a.bot(), (
        f"Bottom identity fail (commute): ({a.bot()} & {a}) != {a.bot()}"
    )
    assert (a.bot() | a) == a, f"Bottom identity fail (join): ({a.bot()} | {a}) != {a}"
    assert (a | a.bot()) == a, (
        f"Bottom identity fail (join commute): ({a} | {a.bot()}) != {a}"
    )


def is_lattice(a: Lattice, b: Lattice, c: Lattice):
    for x in [a, b, c]:
        is_lattice_identities(x)

    if not (a | b <= c):
        # Calculate values for the error message
        assert not (a <= c and b <= c), (
            f"Upper bound check failed: ({a} | {b}) -> {a | b} is not <= {c}. "
            f"Check individual bounds: {a <= c=}, {b <= c=}."
        )

    if not (c <= a & b):
        # Calculate values for the error message
        assert not (c <= a and c <= b), (
            f"Lower bound check failed: {c} is not <= ({a} & {b}) -> {a & b}. "
            f"Check individual bounds: {c <= a=}, {c <= b=}."
        )


class Abstraction(ABC):
    """This is the minimal interface for an abstraction."""

    @classmethod
    @abstractmethod
    def abstract(cls, values: Iterable[jvms.StackValue]) -> Self:
        raise NotImplementedError(f"abstract: {cls}")

    @abstractmethod
    def __contains__(self, value: jvms.StackValue) -> bool: ...


def is_galoi(a: set[jvms.StackValue], b: Abstraction):
    alpha_a = b.abstract(a)

    for value in a:
        assert value in alpha_a, f"{value} not in {a}"

    if alpha_a <= b:
        for value in a:
            assert value in b, f"{value} not in {b}"


type Sign = Literal[-1, 0, 1]


def to_sign(value: jvms.StackValue) -> Sign:
    match value:
        case jvms.StackInt(v):
            return (v > 0) - (v < 0)
        case a:
            raise NotImplementedError(f"Unsupported value {value!r}")


@dataclass(frozen=True, order=True)
class SignSet(Abstraction, Lattice):
    signs: frozenset[Sign]

    def __str__(self):
        return f"{{{''.join(z for z, b in zip('-0+', [-1, 0, 1]) if b in self.signs)}}}"

    def __sexpr__(self):
        return str(self)

    @classmethod
    def from_sign(cls, code):
        return cls(frozenset(b for z, b in zip("-0+", [-1, 0, 1]) if z in code))

    @classmethod
    def abstract(cls, values: Iterable[jvms.StackValue]) -> Self:
        signs = set()
        if not isinstance(values, Iterable):
            values = [values]
        for value in values:
            signs.add(to_sign(value))
        return cls(frozenset(signs))

    def __contains__(self, value: jvms.StackValue) -> bool:
        return to_sign(value) in self.signs

    @classmethod
    def top(cls) -> bool:
        return cls(frozenset([-1, 0, 1]))

    def __or__(self, other: "SignSet") -> "SignSet":
        if not isinstance(other, SignSet):
            return NotImplemented

        return SignSet(self.signs | other.signs)

    def __and__(self, other: "SignSet") -> "SignSet":
        if not isinstance(other, SignSet):
            return NotImplemented

        return SignSet(self.signs & other.signs)

    def arithmetic(self, other: "SignSet", opr: jvm.BinaryOpr) -> tuple["SignSet", set[str]]:
        match opr:
            case jvm.BinaryOpr.Add:
                output = set()
                if 1 in self.signs:
                    output.add(1)
                    if -1 in other.signs:
                        output.update([0, -1])

                if -1 in self.signs:
                    output.add(-1)
                    if 1 in other.signs:
                        output.update([0, 1])

                if 0 in self.signs:
                    output.update(other.signs)

                return (SignSet(output), set())
            case jvm.BinaryOpr.Sub:
                output = set()
                if 1 in self.signs:
                    output.add(1)
                    if 1 in other.signs:
                        output.update([0,-1])
                if 0 in self.signs:
                    if 0 in other.signs:
                        output.add(0)
                    if 1 in other.signs:
                        output.add(-1)
                    if -1 in other.signs:
                        output.add(1)
                if -1 in self.signs:
                    if -1 in other.signs:
                        output.update([0,1,-1])
                    if 0 in other.signs:
                        output.add(-1)
                    if 1 in other.signs:
                        output.add(-1)
                return (SignSet(output), set())
            case jvm.BinaryOpr.Div:
                output = set()
                errors = set()
                has_non_zero_divisor = (1 in other.signs) or (-1 in other.signs)
                if has_non_zero_divisor:
                    if 1 in self.signs:
                        if 1 in other.signs:
                            output.add(1)
                        if -1 in other.signs:
                            output.add(-1)
                        output.add(0)
                    if -1 in self.signs:
                        if 1 in other.signs:
                            output.add(-1)
                        if -1 in other.signs:
                            output.add(1)
                        output.add(0)
                if 0 in self.signs:
                    output.add(0)
                if 0 in other.signs:
                    errors.add("divide by zero")
                return (SignSet(output), errors)
            case jvm.BinaryOpr.Mul:
                output = set()
                if 1 in self.signs:
                    if 1 in other.signs:
                        output.add(1)
                    if -1 in other.signs:
                        output.add(-1)
                if -1 in self.signs:
                    if 1 in other.signs:
                        output.add(-1)
                    if -1 in other.signs:
                        output.add(1)
                if 0 in self.signs:
                    output.add(0)
                if 0 in other.signs:
                    output.add(0)
                return (SignSet(output), set())
            case jvm.BinaryOpr.Rem:
                output = set()
                errors = set()
                has_non_zero_divisor = (1 in other.signs) or (-1 in other.signs)
                if has_non_zero_divisor:
                    if 1 in self.signs:
                        output.update([0, 1])
                    if -1 in self.signs:
                        output.update([0, -1])
                    if 0 in self.signs:
                        output.add(0)

                if 0 in other.signs:
                    errors.add("divide by zero")

                return (SignSet(frozenset(output)), errors)
            

            case _:
                raise NotImplementedError(f"TODO: {opr}")

    def compare(self, other: "SignSet", opr: jvm.CmpOpr) -> Iterable[bool]:
        match opr:
            case jvm.CmpOpr.Le:
                cases = set()
                for x in self.signs:
                    for y in other.signs:
                        if x == 0 or y == 0:
                            cases.add(x <= y)
                            continue
                        if x <= y:
                            cases.add(True)
                        if x >= y:
                            cases.add(False)
                return cases
            case jvm.CmpOpr.Ge:
                cases = set()
                for x in self.signs:
                    for y in other.signs:
                        if x==0 or y==0:
                            cases.add(x>=y)
                            continue
                        if x>=y:
                            cases.add(True)
                        if x<=y:
                            cases.add(False)
                return cases
            case jvm.CmpOpr.Gt:
                cases = set()
                for x in self.signs:
                    for y in other.signs:
                        if x== 0 and y ==0:
                            cases.add(False)
                            continue
                        if x==y:
                            cases.add(True)
                            cases.add(False)
                            continue
                        if x>y:
                            cases.add(True)
                        if x<y:
                            cases.add(False)
                return cases
            case jvm.CmpOpr.Lt:
                cases = set()
                for x in self.signs:
                    for y in other.signs:
                        if x== 0 and y ==0:
                            cases.add(False)
                            continue
                        if x==y:
                            cases.add(True)
                            cases.add(False)
                            continue
                        if x<y:
                            cases.add(True)
                        if x>y:
                            cases.add(False)
                return cases
            case jvm.CmpOpr.Eq:
                cases = set()
                for x in self.signs:
                    for y in other.signs:
                        if x== 0 and y ==0:
                            cases.add(True)
                            continue
                        if x == y:
                            cases.add(True)
                            cases.add(False)
                        
                        if x>y or x<y:
                            cases.add(False)
                return cases
            case jvm.CmpOpr.Ne:
                cases = set()
                for x in self.signs:
                    for y in other.signs:
                        if x== 0 and y == 0:
                            cases.add(False)
                            continue
                        if x==y:
                            cases.add(True)
                            cases.add(False)
                       
                        if x>y or x<y:
                            cases.add(True)
                return cases                        
            case _:
                raise NotImplementedError(f"TODO: {opr}")


from collections.abc import Iterable
from dataclasses import dataclass
from typing import Self


@dataclass(frozen=True)
class Interval(Abstraction, Lattice):
    min: int | None
    max: int | None

    def __str__(self):
        return f"{self.min if self.min is not None else '-inf'}:{self.max if self.max is not None else 'inf'}"

    def __sexpr__(self):
        return str(self)

    @classmethod
    def abstract(cls, values: Iterable[jvms.StackValue]) -> Self:
        if not isinstance(values, Iterable):
            values = [values]
        vals = [v.value if hasattr(v, "value") else v for v in values]
        if not vals:
            return cls(min=1, max=0)
        return cls(min=min(vals), max=max(vals))
    def __contains__(self, value: jvms.StackValue) -> bool:
        val = value.value if hasattr(value, "value") else value
        if self.min is not None and val < self.min:
            return False
        if self.max is not None and val > self.max:
            return False
        return True
    @property
    def is_bot(self) -> bool:
        return self.min is not None and self.max is not None and self.min > self.max
    @classmethod
    def top(cls) -> Self:
        return cls(min=None, max=None)

    def __or__(self, other: "Interval") -> "Interval":
        if self.is_bot: return other
        if other.is_bot: return self
        if self.min is None or other.min is None:
            new_min = None
        else:
            new_min = min(self.min, other.min)
        if self.max is None or other.max is None:
            new_max = None
        else:
            new_max = max(self.max, other.max)
        
        return Interval(min=new_min, max=new_max)

    def __and__(self, other: "Interval") -> "Interval":
        if self.is_bot: return self
        if other.is_bot: return other
        if self.min is None and  other.min is None:
            new_min = None
        elif self.min is None:
            new_min = other.min
        elif other.min is None:
            new_min = self.min
        else:
            new_min = max(self.min, other.min)

        if self.max is None and other.max is None:
            new_max = None
        elif self.max is None:
            new_max = other.max
        elif other.max is None:
            new_max = self.max
        else:
            new_max = min(self.max, other.max)
        result = Interval(min=new_min, max=new_max)
        if result.is_bot:
            return Interval(min=1, max=0)
        return result

    def __lt__(self, other: "Interval") -> bool:
        if self == other:
            return False
        if self.min is None and other.min is None:
            lowerbound = True
        elif self.min is None:
            lowerbound = False
        elif other.min is None:
            lowerbound = True
        else:
            lowerbound = False if self.min < other.min else True

        if self.max is None and other.max is None:
            upperbound = True
        elif self.max is None:
            upperbound = False
        elif other.max is None:
            upperbound = True
        else:
            upperbound = True if self.max <= other.max else False
        return lowerbound and upperbound

    def __gt__(self, other: "Interval") -> bool:
        if self == other:
            return False
        if self.min is None and other.min is None:
            lowerbound = True
        elif self.min is None:
            lowerbound = True
        elif other.min is None:
            lowerbound = False
        else:
            lowerbound = False if self.min > other.min else True

        if self.max is None and other.max is None:
            upperbound = True
        elif self.max is None:
            upperbound = True
        elif other.max is None:
            upperbound = False
        else:
            upperbound = True if self.max >= other.max else False
        return lowerbound and upperbound

    def __eq__(self, other: "Interval") -> bool:
        return self.min == other.min and self.max == other.max
    def __add__(self, other: "Interval") -> "Interval":
        if self.is_bot: return other
        if other.is_bot: return self
        new_min = None
        new_max = None
        if self.min is not None and other.min is not None:
            new_min = self.min + other.min
        else:
            new_min = None
        if self.max is not None and other.max is not None:
            new_max = self.max + other.max
        else:
            new_max = None
        return Interval(min=new_min, max=new_max)
    def __sub__(self, other: "Interval") -> "Interval":
        if self.is_bot: return other
        if other.is_bot: return self
        new_min = None
        new_max = None
        if self.min is not None and other.max is not None:
            new_min = self.min - other.max
        else:
            new_min = None

        if self.max is not None and other.min is not None:
            new_max = self.max - other.min
        else:
            new_max = None

        return Interval(min=new_min, max=new_max)

    def __truediv__(self, other: "Interval") -> "Interval":

        if self.is_bot: return self
        if other.is_bot: return self

        if other.min == 0 and other.max == 0:
            return Interval(min=1, max=0)
        
        contains_zero = (other.min is None or other.min <= 0) and (other.max is None or other.max >= 0)
        if contains_zero:
            return Interval(min=None, max=None) # if 0 is a possibility in the divisor, the result can be unbounded (infinity)

       
        if self.min is None or self.max is None or other.min is None or other.max is None:
            return Interval(min=None, max=None) # if any of the bounds are unbounded, the result can be unbounded (infinity)

        def java_div(x: int, y: int) -> int:
            """Java division rounds towards zero, Python's // rounds down."""
            quotient = abs(x) // abs(y)
            return quotient if (x < 0) == (y < 0) else -quotient

        # all possible bounds
        corners = [
            java_div(self.min, other.min),
            java_div(self.min, other.max),
            java_div(self.max, other.min),
            java_div(self.max, other.max)
        ]
        
        return Interval(min=min(corners), max=max(corners))
    def __mul__(self,other: "Interval") -> "Interval":
        if self.is_bot: return self
        if other.is_bot: return self
        if self.min is None or self.max is None or other.min is None or other.max is None:
            return Interval(min=None, max=None) # if any of the bounds are unbounded, the result can be unbounded (infinity)
        # all possible bounds
        corners = [
            self.min * other.min,
            self.min * other.max,
            self.max * other.min,
            self.max * other.max
        ]        
        return Interval(min=min(corners), max=max(corners))
    def __mod__(self, other: "Interval") -> "Interval":
        if self.is_bot: return self
        if other.is_bot: return other

        if other.min == 0 and other.max == 0:
            return Interval(min=1, max=0)

        # A Java remainder has the sign of the dividend. Ignoring the sign, it is
        # at most the dividend and less than the divisor.
        lows = [] if self.min is None else [min(self.min, 0)]
        highs = [] if self.max is None else [max(self.max, 0)]
        if other.min is not None and other.max is not None:
            limit = max(abs(other.min), abs(other.max)) - 1
            lows.append(-limit)
            highs.append(limit)
        return Interval(min=max(lows, default=None), max=min(highs, default=None))

    def wrap_int(self) -> "Interval":
        """The Java ints left after the numbers in this interval overflow."""
        sign_bit = 2**31
        if self.is_bot:
            return self
        if self.min is None or self.max is None:
            return Interval(-sign_bit, sign_bit - 1)
        first_wrap, low = divmod(self.min + sign_bit, 2**32)
        last_wrap, high = divmod(self.max + sign_bit, 2**32)
        if first_wrap != last_wrap:
            return Interval(-sign_bit, sign_bit - 1)
        return Interval(low - sign_bit, high - sign_bit)

    def arithmetic(self, other: "Interval", opr: jvm.BinaryOpr) -> tuple["Interval", set[str]]:
        """The Java int operation: both operands are ints, and the result wraps around."""
        errors = set()
        ints = Interval(-(2**31), 2**31 - 1)
        self, other = self & ints, other & ints
        match opr:
            case jvm.BinaryOpr.Add:
                res = self + other
            case jvm.BinaryOpr.Sub:
                res = self - other
            case jvm.BinaryOpr.Mul:
                res = self * other
            case jvm.BinaryOpr.Div:
                res = self / other
                if other.min == 0 and other.max == 0:
                    errors.add("divide by zero")
                elif (other.min is None or other.min <= 0) and (other.max is None or other.max >= 0):
                    errors.add("divide by zero")
            case jvm.BinaryOpr.Rem:
                res = self % other
                if other.min == 0 and other.max == 0:
                    errors.add("divide by zero")
                elif (other.min is None or other.min <= 0) and (other.max is None or other.max >= 0):
                    errors.add("divide by zero")
            case _:
                raise NotImplementedError(f"Unsupported operation: {opr}")

        return res.wrap_int(), errors
    def bitwise(self, other: "Interval", opr: jvm.BitOpr) -> "Interval":
        if self.is_bot:
            return self
        if other.is_bot:
            return other

        INT_MIN = -(2**31)
        INT_MAX = 2**31 - 1
        INT_MASK = 2**32 - 1

        def signed32(value: int) -> int:
            value &= INT_MASK
            return value if value < 2**31 else value - 2**32

        if (
            self.min is None or self.max is None
            or other.min is None or other.max is None
        ):
            return Interval(min=INT_MIN, max=INT_MAX)

        left_values = range(self.min, self.max + 1)
        right_values = range(other.min, other.max + 1)
        left_count = self.max - self.min + 1
        right_count = other.max - other.min + 1
        if left_count * right_count > 65536:
            return Interval(min=INT_MIN, max=INT_MAX)

        results = set()
        for left in left_values:
            for right in right_values:
                match opr:
                    case jvm.BitOpr.Shl:
                        results.add(signed32(left << (right & 0b11111)))
                    case jvm.BitOpr.Shr:
                        results.add(signed32(left >> (right & 0b11111)))
                    case jvm.BitOpr.Ushr:
                        results.add(signed32((left & INT_MASK) >> (right & 0b11111)))
                    case jvm.BitOpr.And:
                        results.add(signed32(left & right))
                    case jvm.BitOpr.Or:
                        results.add(signed32(left | right))
                    case jvm.BitOpr.Xor:
                        results.add(signed32(left ^ right))
                    case _:
                        raise NotImplementedError(f"Unsupported operation: {opr}")

        if not results:
            return Interval.bot()
        return Interval(min=min(results), max=max(results))
    def compare(self, other: "Interval", opr: jvm.CmpOpr) -> Iterable[bool]:
        if self.is_bot or other.is_bot:
            return []

        match opr:
            case jvm.CmpOpr.Le: 
                if self.max is not None and other.min is not None and self.max <= other.min:
                    return [True]
                if self.min is not None and other.max is not None and self.min > other.max:
                    return [False]
                return [True, False]

            case jvm.CmpOpr.Ge: 
                if self.min is not None and other.max is not None and self.min >= other.max:
                    return [True]
                if self.max is not None and other.min is not None and self.max < other.min:
                    return [False]
                return [True, False]

            case jvm.CmpOpr.Gt: 
                if self.min is not None and other.max is not None and self.min > other.max:
                    return [True]
                if self.max is not None and other.min is not None and self.max <= other.min:
                    return [False]
                return [True, False]

            case jvm.CmpOpr.Lt: 
                if self.max is not None and other.min is not None and self.max < other.min:
                    return [True]
                if self.min is not None and other.max is not None and self.min >= other.max:
                    return [False]
                return [True, False]

            case jvm.CmpOpr.Eq: 
                
                if (self.max is not None and other.min is not None and self.max < other.min) or \
                   (self.min is not None and other.max is not None and self.min > other.max):
                    return [False]
               
                if self.min == self.max == other.min == other.max and self.min is not None:
                    return [True]
                return [True, False]

            case jvm.CmpOpr.Ne: # 
                
                if (self.max is not None and other.min is not None and self.max < other.min) or \
                   (self.min is not None and other.max is not None and self.min > other.max):
                    return [True]
              
                if self.min == self.max == other.min == other.max and self.min is not None:
                    return [False]
                return [True, False]
    def widen(self, other: "Interval",K:list[int]) -> "Interval":
        if self.is_bot: return other
        if other.is_bot: return self
        if K is None:
            K = [] 
        if self.min is None or other.min is None or other.min < self.min:
         
            candidates = [k for k in K if other.min is not None and k <= other.min]
            new_min = max(candidates) if candidates else None
        else:
            new_min = self.min
        if self.max is None or other.max is None or other.max > self.max:
          
            candidates = [k for k in K if other.max is not None and k >= other.max]
            new_max = min(candidates) if candidates else None
        else:
            new_max = self.max
            
        return Interval(min=new_min, max=new_max)


@dataclass(frozen=True, eq=False)
class Drawn(Interval):
    """An interval whose bits come from a Smith draw.

    After a mask or shift, sources maps each result bit to its Smith
    position, with None for bits that are always zero.
    """

    start: int = 0
    width: int = 0
    sources: tuple[int | None, ...] | None = None

    def bit_sources(self) -> tuple[int | None, ...]:
        if self.sources is not None:
            return self.sources
        return tuple(self.start + self.width - bit - 1 if bit < self.width else None
                     for bit in range(32))

    def bitwise(self, other: Interval, opr: jvm.BitOpr) -> Interval:
        result = super().bitwise(other, opr)
        if result.is_bot or other.min is None or other.min != other.max:
            return result
        constant = other.min
        sources = self.bit_sources()
        shift = constant & 31
        match opr:
            case jvm.BitOpr.And:
                sources = tuple(source if constant & (1 << bit) else None
                                for bit, source in enumerate(sources))
            case jvm.BitOpr.Shl:
                sources = (None,) * shift + sources[:32 - shift]
            case jvm.BitOpr.Ushr:
                sources = sources[shift:] + (None,) * shift
            case jvm.BitOpr.Shr:
                sources = sources[shift:] + (sources[-1],) * shift
            case _:
                return result
        return Drawn(result.min, result.max, self.start, self.width, sources)

    def __or__(self, other: Interval) -> Interval:
        result = super().__or__(other)
        if isinstance(other, Drawn) and self.bit_sources() == other.bit_sources():
            return Drawn(result.min, result.max, self.start, self.width, self.sources)
        return result


@dataclass(frozen=True)
class AbstractSmith(Abstraction, Lattice):
    """Abstract Smith: a set of possible bitstrings plus how many bits are read.

    pattern: one char per position, '0', '1' or '?' (unknown).
             Positions past the end of the pattern are '?'.
    length:  possible lengths of the bitstring.
    cursor:  possible number of bits asked for so far. Bits past the end
             read as 0 wherever they are, so the cursor may run past the
             end; Java's real index is min(cursor, length).
    """

    pattern: str
    length: Interval
    cursor: Interval

    def __post_init__(self):
        # Keep one representation per value, so == works:
        # all bottoms look the same, and "01??" is stored as "01".
        if self.length.is_bot or self.cursor.is_bot:
            object.__setattr__(self, "pattern", "")
            object.__setattr__(self, "length", Interval.bot())
            object.__setattr__(self, "cursor", Interval.bot())
        else:
            # bits past the longest possible end never matter
            pattern = self.pattern if self.length.max is None else self.pattern[: self.length.max]
            object.__setattr__(self, "pattern", pattern.rstrip("?"))

    def __str__(self):
        return f"smith({self.pattern or '?'}, len={self.length}, at={self.cursor})"

    def __sexpr__(self):
        return str(self)

    @property
    def is_bot(self) -> bool:
        return self.cursor.is_bot

    def bit(self, k: int) -> str:
        return self.pattern[k] if k < len(self.pattern) else "?"

    # --- constructors ---

    @classmethod
    def top(cls) -> Self:
        return cls("", Interval(0, None), Interval(0, None))

    @classmethod
    def bot(cls) -> Self:
        return cls("", Interval.bot(), Interval.bot())

    @classmethod
    def unknown(cls) -> Self:
        """Any bitstring, nothing read yet. Start state for analyse()."""
        return cls("", Interval(0, None), Interval(0, 0))

    @classmethod
    def from_bits(cls, bits: str) -> Self:
        """Exactly one bitstring, nothing read yet. Start state for interpret()."""
        return cls(bits, Interval(len(bits), len(bits)), Interval(0, 0))

    # --- Galois connection: concrete values are (bits, index) pairs ---

    @classmethod
    def abstract(cls, values: Iterable[tuple[str, int]]) -> Self:
        result = cls.bot()
        for bits, index in values:
            n = len(bits)
            result = result | cls(bits, Interval(n, n), Interval(index, index))
        return result

    def __contains__(self, value: tuple[str, int]) -> bool:
        bits, index = value
        return (
            len(bits) in self.length
            and index <= len(bits)
            # the real index is min(cursor, len(bits)) for some cursor value
            and (index in self.cursor if index < len(bits)
                 else self.cursor.max is None or self.cursor.max >= index)
            and all(p == "?" or k >= len(bits) or bits[k] == p for k, p in enumerate(self.pattern))
        )

    # --- lattice ---

    def __le__(self, other: "AbstractSmith") -> bool:
        if self.is_bot:
            return True
        if other.is_bot:
            return False
        same_bits = all(p == "?" or self.bit(k) == p for k, p in enumerate(other.pattern))
        return (
            same_bits
            and (self.length & other.length) == self.length
            and (self.cursor & other.cursor) == self.cursor
        )

    def __lt__(self, other: "AbstractSmith") -> bool:
        return self <= other and self != other

    def __gt__(self, other: "AbstractSmith") -> bool:
        return other < self

    def __or__(self, other: "AbstractSmith") -> "AbstractSmith":
        if self.is_bot:
            return other
        if other.is_bot:
            return self
        size = max(len(self.pattern), len(other.pattern))
        pattern = "".join(
            self.bit(k) if self.bit(k) == other.bit(k) else "?" for k in range(size)
        )
        return AbstractSmith(pattern, self.length | other.length, self.cursor | other.cursor)

    def __and__(self, other: "AbstractSmith") -> "AbstractSmith":
        if self.is_bot or other.is_bot:
            return AbstractSmith.bot()
        bits = []
        for k in range(max(len(self.pattern), len(other.pattern))):
            a, b = self.bit(k), other.bit(k)
            if a != "?" and b != "?" and a != b:
                return AbstractSmith.bot()  # the bitstrings disagree on bit k
            bits.append(b if a == "?" else a)
        return AbstractSmith("".join(bits), self.length & other.length, self.cursor & other.cursor)

    def widen(self, other: "AbstractSmith", K: list[int]) -> "AbstractSmith":
        if self.is_bot:
            return other
        if other.is_bot:
            return self
        # The pattern never grows, so only the intervals need widening.
        return AbstractSmith(
            (self | other).pattern,
            self.length.widen(other.length, K),
            self.cursor.widen(other.cursor, K),
        )

    # --- the abstract draw ---

    def draw(self, n: int) -> tuple[Interval, "AbstractSmith"] | None:
        """Read n bits with zero padding. The cursor always moves n forward:
        past the end every bit is 0, so it does not matter that Java's index
        stops at the end, and an exact cursor stays exact."""
        if self.is_bot:
            return None
        value = self.read(self.cursor, n)
        if self.cursor.min is not None and self.cursor.min == self.cursor.max and n <= 32:
            value = Drawn(value.min, value.max, self.cursor.min, n)
        return value, AbstractSmith(self.pattern, self.length, self.cursor + Interval(n, n))

    def draw_counts(self, count: Interval) -> tuple[Interval, "AbstractSmith"] | None:
        """Read any number of bits in a nonnegative count interval."""
        if self.is_bot or count.is_bot:
            return None
        if count.min is not None and count.min == count.max:
            return self.draw(count.min)

        # Intermediate counts can produce values outside the endpoint reads.
        if count.max is None or count.max >= 32:
            value = Interval(-(2**31), 2**31 - 1)
        else:
            value = Interval(0, 2**count.max - 1)
        return value, AbstractSmith(self.pattern, self.length, self.cursor + count)

    def learn(self, start: int, width: int, value: Interval) -> "AbstractSmith":
        """A branch narrowed the value read from bits [start, start + width)
        to `value`. Keep only the bitstrings that agree: the bits shared by
        every number in the range become known.

        Missing bits read as 0, so a learned 1 means the bitstring really is
        that long, and a learned 0 where the pattern says 1 means the
        bitstring ended before that bit.
        """
        if self.is_bot or value.is_bot:
            return AbstractSmith.bot()
        if width >= 32:  # ponytail: signed 32-bit reads learn nothing; split the range by sign if needed
            return self
        lo = 0 if value.min is None else max(value.min, 0)
        hi = 2**width - 1 if value.max is None else min(value.max, 2**width - 1)
        if lo > hi:
            return AbstractSmith.bot()

        pattern = list(self.pattern.ljust(start + width, "?"))
        length = self.length
        for shift in reversed(range(width)):
            if lo >> shift != hi >> shift:
                break  # the numbers in the range differ from this bit on
            k = start + width - 1 - shift
            if (lo >> shift) & 1:
                if pattern[k] == "0":
                    return AbstractSmith.bot()
                pattern[k] = "1"
                length = length & Interval(k + 1, None)
            elif pattern[k] == "1":
                length = length & Interval(None, k)
            else:
                pattern[k] = "0"
        return AbstractSmith("".join(pattern), length, self.cursor)

    def learn_sources(self, sources: tuple[int | None, ...], value: Interval) -> "AbstractSmith":
        """Use the endpoints' shared leading bits to constrain the Smith input."""
        bounds = value & Interval(-(2**31), 2**31 - 1)
        if bounds.is_bot:
            return AbstractSmith.bot()

        smith = self
        for bit_index, source in zip(range(31, -1, -1), reversed(sources)):
            lower_bit = (bounds.min >> bit_index) & 1
            upper_bit = (bounds.max >> bit_index) & 1
            if lower_bit != upper_bit:
                break

            if source is not None:
                smith = smith.learn(source, 1, Interval(lower_bit, lower_bit))
            elif lower_bit == 1:
                return AbstractSmith.bot()
        return smith

    def read(self, cursor: Interval, n: int) -> Interval:
        """Bound the signed Java int formed by the last 32 bits of the draw."""
        width = min(n, 32)
        if cursor.min is None or cursor.min != cursor.max:
            if width == 32:
                return Interval(-(2**31), 2**31 - 1)
            return Interval(0, 2**width - 1)

        end = cursor.min + n
        low = high = 0
        for position in range(end - width, end):
            if self.length.max is not None and position >= self.length.max:
                continue
            bit = self.bit(position)
            weight = 1 << (end - position - 1)
            if weight == 2**31:
                weight = -weight
            if bit == "1" and self.length.min is not None and position < self.length.min:
                low += weight
                high += weight
            elif bit != "0":
                low += min(weight, 0)
                high += max(weight, 0)
        return Interval(low, high)
