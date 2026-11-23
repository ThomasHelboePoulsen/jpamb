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

        # all possible bounds
        corners = [
            self.min // other.min,
            self.min // other.max,
            self.max // other.min,
            self.max // other.max
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

        # Calculate the lowest possible remainder
        if other.min is None:
            new_min = None
        elif other.min < 0:
            new_min = other.min + 1  
        else:
            new_min = 0              

        # Calculate the highest possible remainder
        if other.max is None:
            new_max = None
        elif other.max > 0:
            new_max = other.max - 1 
        else:
            new_max = 0              
        return Interval(min=new_min, max=new_max)

    def arithmetic(self, other: "Interval", opr: jvm.BinaryOpr) -> tuple["Interval", set[str]]:
        errors = set()
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
                
        return res, errors
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


@dataclass(frozen=True)
class AbstractSmith(Abstraction, Lattice):
    """Abstract Smith: a set of possible bitstrings plus how many bits are read.

    pattern: one char per position, '0', '1' or '?' (unknown).
             Positions past the end of the pattern are '?'.
    length:  possible lengths of the bitstring.
    cursor:  possible number of bits read so far.
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
            object.__setattr__(self, "pattern", self.pattern.rstrip("?"))

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
            and index in self.cursor
            and index <= len(bits)
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

    def draw(self, n: int) -> tuple[tuple[Interval, "AbstractSmith"] | None, "AbstractSmith | None"]:
        """Abstract Smith.draw(n). draw() is draw(1).

        Returns (success, exhausted):
          success:   (value, smith after the read), or None if the read can never succeed.
          exhausted: smith when the bits run out, or None if that can never happen.
        """
        assert 0 <= n <= 32, "count must be between 0 and 32"
        if self.is_bot:
            return None, None
        step = Interval(n, n)
        end = self.cursor + step

        # Success needs cursor + n <= length.
        length = self.length & Interval(end.min, None)
        cursor = self.cursor
        if length.max is not None:
            cursor = cursor & Interval(None, length.max - n)
        success = None
        if not (length.is_bot or cursor.is_bot):
            after = AbstractSmith(self.pattern, length, cursor + step)
            success = (self.read(cursor, n), after)

        # Exhaustion needs cursor + n > length.
        length = self.length
        if end.max is not None:
            length = length & Interval(None, end.max - 1)
        cursor = self.cursor
        if self.length.min is not None:
            cursor = cursor & Interval(self.length.min - n + 1, None)
        exhausted = None
        if not (length.is_bot or cursor.is_bot):
            exhausted = AbstractSmith(self.pattern, length, cursor)

        return success, exhausted

    def read(self, cursor: Interval, n: int) -> Interval:
        """Possible values of n bits read from position cursor."""
        if cursor.min is not None and cursor.min == cursor.max:
            bits = [self.bit(cursor.min + k) for k in range(n)]
            if "?" not in bits:
                value = int("".join(bits), 2) if bits else 0
                if value >= 2**31:  # Java int overflow: bit 31 is the sign
                    value -= 2**32
                return Interval(value, value)
        # ponytail: inexact cursor gives the full range. Upgrade: join the
        # reading at each possible cursor position.
        if n == 32:
            return Interval.top()
        return Interval(0, 2**n - 1)