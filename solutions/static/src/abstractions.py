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

    

# ---------------------------------------------------------------------------
# Smith / bit-vector abstraction
#
# Concrete domain: sets of bitstrings, i.e. the inputs a Smith may wrap.
# Abstract domain: BitPattern = one trit per position (0, 1 or None = unknown)
# plus an Interval over the length of the bitstring.
#
#   alpha(S) = (bits on which every long-enough string of S agrees, hull of the lengths)
#   gamma(p) = { s | len(s) in p.length and s[i] == p.bits[i]
#                    for every known p.bits[i] with i < len(s) }
#
# Positions past len(bits) are unknown. Positions at or past length.max exist
# in no string of gamma(p); they carry no information, so bits are cut there
# (with trailing unknowns stripped) to give one representation per value.
# ---------------------------------------------------------------------------

type Trit = Literal[0, 1] | None


def _interval_le(a: Interval, b: Interval) -> bool:
    """Interval inclusion a ⊑ b."""
    if a.is_bot:
        return True
    if b.is_bot:
        return False
    lo = b.min is None or (a.min is not None and a.min >= b.min)
    hi = b.max is None or (a.max is not None and a.max <= b.max)
    return lo and hi


@dataclass(frozen=True)
class BitPattern(Abstraction, Lattice):
    bits: tuple[Trit, ...]
    length: Interval

    def __post_init__(self):
        length = Interval(1, 0) if self.length.is_bot else self.length
        bits = () if length.is_bot else tuple(self.bits[: length.max])
        while bits and bits[-1] is None:
            bits = bits[:-1]
        object.__setattr__(self, "bits", bits)
        object.__setattr__(self, "length", length)

    def __str__(self):
        if self.is_bot:
            return "⊥"
        tail = "" if self.length.max == len(self.bits) else "?*"
        return "".join("?" if b is None else str(b) for b in self.bits) + f"{tail} len {self.length}"

    def __sexpr__(self):
        return str(self)

    @property
    def is_bot(self) -> bool:
        return self.length.is_bot

    def bit(self, i: int) -> Trit:
        return self.bits[i] if i < len(self.bits) else None

    def _exists(self, i: int) -> bool:
        """Can position i exist in some string of gamma(self)?"""
        return not self.is_bot and (self.length.max is None or i < self.length.max)

    @classmethod
    def top(cls) -> Self:
        return cls((), Interval(0, None))

    @classmethod
    def bot(cls) -> Self:
        return cls((), Interval(1, 0))

    @classmethod
    def abstract(cls, values: Iterable[str]) -> Self:
        values = list(values)
        if not values:
            return cls.bot()
        n = max(map(len, values))
        bits = []
        for i in range(n):
            seen = {int(s[i]) for s in values if i < len(s)}
            bits.append(seen.pop() if len(seen) == 1 else None)
        return cls(tuple(bits), Interval(min(map(len, values)), n))

    def __contains__(self, value: str) -> bool:
        return len(value) in self.length and all(
            b is None or int(value[i]) == b
            for i, b in enumerate(self.bits)
            if i < len(value)
        )

    def _le(self, other: "BitPattern") -> bool:
        if not _interval_le(self.length, other.length):
            return False
        return all(
            b is None or not self._exists(i) or self.bit(i) == b
            for i, b in enumerate(other.bits)
        )

    def __eq__(self, other: "BitPattern") -> bool:
        return self.bits == other.bits and self.length == other.length

    def __lt__(self, other: "BitPattern") -> bool:
        return self._le(other) and self != other

    def __gt__(self, other: "BitPattern") -> bool:
        return other < self

    def __or__(self, other: "BitPattern") -> "BitPattern":
        if self.is_bot:
            return other
        if other.is_bot:
            return self
        bits = []
        for i in range(max(len(self.bits), len(other.bits))):
            if not self._exists(i):  # absent position acts as ⊥
                bits.append(other.bit(i))
            elif not other._exists(i):
                bits.append(self.bit(i))
            else:
                a, b = self.bit(i), other.bit(i)
                bits.append(a if a == b else None)
        return BitPattern(tuple(bits), self.length | other.length)

    def __and__(self, other: "BitPattern") -> "BitPattern":
        length = self.length & other.length
        bits = []
        for i in range(max(len(self.bits), len(other.bits))):
            a, b = self.bit(i), other.bit(i)
            if a is not None and b is not None and a != b:
                # No string can have position i: they all end before it.
                length = length & Interval(None, i)
                break
            bits.append(a if a is not None else b)
        return BitPattern(tuple(bits), length)

    def widen(self, other: "BitPattern", K: list[int]) -> "BitPattern":
        # Trits have finite height; only the length can grow forever.
        if self.is_bot:
            return other
        if other.is_bot:
            return self
        return BitPattern((self | other).bits, self.length.widen(other.length, K))

    def read(self, start: int, width: int) -> Interval:
        """Unsigned value range of bits [start, start + width), MSB first."""
        lo = hi = 0
        for i in range(start, start + width):
            b = self.bit(i)
            lo = lo * 2 + (0 if b is None else b)
            hi = hi * 2 + (1 if b is None else b)
        return Interval(lo, hi)

    def with_slice(self, start: int, width: int, value: Interval) -> "BitPattern":
        """Meet with the bits shared by every unsigned value of `value` in [start, start + width)."""
        if value.is_bot:
            return BitPattern.bot()
        if width >= 32:  # ponytail: signed 32-bit draws give no bit facts; split the range per sign if needed
            return self
        lo = max(value.min if value.min is not None else 0, 0)
        hi = min(value.max if value.max is not None else 2**width - 1, 2**width - 1)
        if lo > hi:
            return BitPattern.bot()
        bits: list[Trit] = [None] * start
        for shift in reversed(range(width)):
            if lo >> shift != hi >> shift:
                break
            bits.append((lo >> shift) & 1)
        return self & BitPattern(tuple(bits), Interval(0, None))

    def witness(self) -> str | None:
        """One concrete (shortest) bitstring in gamma(self); unknown bits become 0."""
        if self.is_bot:
            return None
        return "".join(str(self.bit(i) or 0) for i in range(self.length.min))


@dataclass(frozen=True, eq=False)
class Drawn(Interval):
    """An Interval produced directly by a Smith draw. It remembers which bits
    produced it, so branch conditions on the value can refine those bits."""

    tag: int = 0
    start: int = 0
    width: int = 0


@dataclass(frozen=True)
class AbstractSmith:
    """Abstract Smith object: the bitstrings it may wrap and where its cursor
    may be. `tag` names the concrete Smith object (its parameter slot), so
    aliases and joined states agree on which object is meant."""

    tag: int
    pattern: BitPattern
    cursor: Interval
    is_bot = False  # lets Interval.__or__ treat it as a non-bottom value

    def __str__(self):
        return f"smith{self.tag}<{self.pattern} @ {self.cursor}>"

    def __sexpr__(self):
        return str(self)

    def __or__(self, other):
        if isinstance(other, Interval) and other.is_bot:
            return self
        assert isinstance(other, AbstractSmith) and other.tag == self.tag, f"cannot join {self} with {other}"
        return AbstractSmith(self.tag, self.pattern | other.pattern, self.cursor | other.cursor)

    def widen(self, other, K: list[int]) -> "AbstractSmith":
        if isinstance(other, Interval) and other.is_bot:
            return self
        return AbstractSmith(self.tag, self.pattern.widen(other.pattern, K), self.cursor.widen(other.cursor, K))

    def draw(self, count: int) -> tuple[tuple[Interval, "AbstractSmith"] | None, "AbstractSmith | None"]:
        """Abstract Smith.draw(count) (count bits as an int; draw() is count=1).

        Returns (success, exhausted):
          success   = (value, smith after the draw), or None if the draw must fail
          exhausted = smith on the IllegalStateException path, or None if it cannot happen
        """
        success = None
        enough = self.pattern & BitPattern((), Interval(self.cursor.min + count, None))
        if not enough.is_bot:
            c = self.cursor.min
            if c == self.cursor.max:
                value = enough.read(c, count)
                if count == 32:  # reinterpret as a signed Java int
                    if value.min >= 2**31:
                        value = Interval(value.min - 2**32, value.max - 2**32)
                    elif value.max >= 2**31:
                        value = Interval.top()
                if count < 32:
                    value = Drawn(value.min, value.max, self.tag, c, count)
            else:
                value = Interval(0, 2**count - 1) if count < 32 else Interval.top()
            success = (value, AbstractSmith(self.tag, enough, self.cursor + Interval(count, count)))

        exhausted = None
        if self.cursor.max is None:
            exhausted = self
        else:
            short = self.pattern & BitPattern((), Interval(0, self.cursor.max + count - 1))
            if not short.is_bot:
                exhausted = AbstractSmith(self.tag, short, self.cursor)
        return success, exhausted
