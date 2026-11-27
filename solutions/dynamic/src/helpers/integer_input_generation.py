from collections.abc import Iterable, Iterator
from itertools import islice
import random

from tree_sitter import Node

import jpamb
import jvm
from helpers.dynamic_java_literals import INT_MAX, INT_MIN, integer_candidates, method_body

IntegerOperation = tuple[str, int]
ARITHMETIC_SEED_LIMIT = 128
ARITHMETIC_SEED_ROUNDS = 10


def integer_literal(node: Node) -> int | None:
    match node.type:
        case "parenthesized_expression":
            expression = next(child for child in node.named_children if not child.is_extra)
            return integer_literal(expression)
        case "unary_expression":
            operator = node.child_by_field_name("operator").type
            if operator in {"+", "-"}:
                operand = integer_literal(node.child_by_field_name("operand"))
                if operand is not None:
                    return operand if operator == "+" else -operand
        case "decimal_integer_literal" | "hex_integer_literal":
            digits = node.text.decode().replace("_", "")
            if not digits.endswith(("l", "L")):
                base = 16 if node.type == "hex_integer_literal" else 10
                value = int(digits, base)
                return value - 2**32 if base == 16 and value > INT_MAX else value
    return None


def get_integer_operations(methodid: jvm.AbsMethodID, suite: jpamb.Suite) -> tuple[IntegerOperation, ...]:
    '''Finds all integer operations and the constant values used in them'''
    has_int_or_smith = any(
        p == jvm.Int() or (isinstance(p, jvm.Object) and "Smith" in str(p.name))
        for p in methodid.extension.params
    )
    if not has_int_or_smith:
        return ()

    operations = set()
    pending = [method_body(methodid, suite)]
    while pending:
        node = pending.pop()
        pending.extend(node.named_children)
        if node.type not in {"binary_expression", "assignment_expression"}:
            continue
        operator = node.child_by_field_name("operator").type.removesuffix("=")
        if operator not in {"+", "-", "*", "/"}:
            continue

        operands = [node.child_by_field_name("right")]
        if node.type == "binary_expression" and operator in {"+", "*"}:
            operands.append(node.child_by_field_name("left"))
        for operand in operands:
            value = integer_literal(operand)
            if value is not None and INT_MIN <= value <= INT_MAX:
                operations.add((operator, value))
    return tuple(sorted(operations))


def arithmetic_neighbors(value: int, operations: tuple[IntegerOperation, ...]) -> set[int]:
    """Generates integer neighbours by applying operation with value to input value"""
    candidates = set()
    for operator, operand in operations:
        if operator in {"+", "-"}:
            candidates.update((value + operand, value - operand))
        else:
            candidates.add(value * operand)
            if operand != 0:
                quotient = abs(value) // abs(operand)
                candidates.add(-quotient if (value < 0) != (operand < 0) else quotient)
    candidates.discard(value)
    return {candidate for candidate in candidates if INT_MIN <= candidate <= INT_MAX}


def arithmetic_seed_values(
    literals: list[int], operations: tuple[IntegerOperation, ...]
) -> Iterator[int]:
    previous_round = set(literals)
    seen = set(previous_round)
    dictionary_values = set(integer_candidates({int: literals}))
    for _ in range(ARITHMETIC_SEED_ROUNDS):
        candidates = {
            candidate
            for value in previous_round
            for candidate in arithmetic_neighbors(value, operations)
        }
        new_values = candidates - seen
        if not new_values:
            return
        seen.update(new_values)
        previous_round = new_values
        yield from sorted(new_values - dictionary_values, key=lambda value: (abs(value), value))


def inputs_with_one_integer_seed(
    template: jpamb.case.Input, seed_values: Iterable[int]
) -> Iterator[jpamb.case.Input]:
    default_arguments = list(template.values)
    integer_indices = []
    for index, argument in enumerate(default_arguments):
        if isinstance(argument, jpamb.case.Int):
            integer_indices.append(index)
            default_arguments[index] = jpamb.case.Int(0)
    if not integer_indices:
        return

    for value in seed_values:
        for index in integer_indices:
            arguments = default_arguments.copy()
            arguments[index] = jpamb.case.Int(value)
            yield jpamb.case.Input(tuple(arguments))


def arithmetic_inputs(
    template: jpamb.case.Input, literals: list[int], operations: tuple[IntegerOperation, ...]
) -> Iterator[jpamb.case.Input]:
    if not operations:
        return

    seed_values = arithmetic_seed_values(literals, operations)
    inputs = inputs_with_one_integer_seed(template, seed_values)
    yield from islice(inputs, ARITHMETIC_SEED_LIMIT)


def mutate_integer(value: int, operations: tuple[IntegerOperation, ...], *, rand=random) -> int:
    if operations and rand.random() < 0.75:
        candidates = arithmetic_neighbors(value, operations)
        if candidates:
            return rand.choice(sorted(candidates))

    mutated = value + rand.choice((-1, 0, 1))
    return (mutated - INT_MIN) % (2**32) + INT_MIN
