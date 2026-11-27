from dataclasses import dataclass, field
from itertools import islice
import os
import random
import string

import jpamb
import jvm
from abstractions import AbstractSmith
from static import SMITH_TYPE, abstract_analysis_results

from helpers.bitstring_structure import get_bitstring_structure
from helpers.bitstring_input_generation import generate_bitstring_inputs
from helpers.dynamic_java_literals import (
    convert_literals,
    generate_inputs_from_dict,
    get_literals_in_method,
)
from helpers.integer_input_generation import (
    IntegerOperation,
    arithmetic_inputs,
    arithmetic_seed_values,
    get_integer_operations,
)

MAX_SMITH_SEED_LENGTH = 10_000


@dataclass
class FuzzContext:
    dictionary: dict
    structure: list
    smith_results: dict[str, list[AbstractSmith]]
    integer_operations: tuple[IntegerOperation, ...]
    initial_seeds: list[jpamb.case.Input]
    use_dynamic_structure: bool = True
    corpus: list[jpamb.case.Input] = field(default_factory=list)
    used_corpus: set[jpamb.case.Input] = field(default_factory=set)
    queued_inputs: list[jpamb.case.Input] = field(default_factory=list)
    pc_coverage: set = field(default_factory=set)
    behaviors: set[str] = field(default_factory=set)


def _env_disabled(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


def fuzz_input(rand: random.Random, methodid: jvm.AbsMethodID) -> jpamb.case.Input:
    input = []

    for p in methodid.extension.params:
        match p:
            case jvm.Int():
                input.append(jpamb.case.Int(rand.randint(-(1 << 31), 1 << 31)))

            case jvm.Boolean():
                input.append(jpamb.case.Boolean(1 == rand.randint(0, 1)))
            case jvm.Array(contains=jvm.Int()):
                rand_upperbound = rand.randint(1, 10000)
                rand_length = rand.randint(0, rand_upperbound)
                array = []
                for i in range(rand_length):
                    rand_val = rand.randint(-(1 << 31), 1 << 31)
                    array.append(rand_val)
                input.append(jpamb.case.Array(jvm.Int(), tuple(array)))
            case jvm.Array(contains=jvm.Char()):
                rand_upperbound = rand.randint(1, 10000)
                rand_length = rand.randint(0, rand_upperbound)
                array = []
                for i in range(rand_length):
                    random_int = rand.randint(32, 126)
                    rand_char = chr(random_int)
                    array.append(rand_char)
                input.append(jpamb.case.Array(jvm.Char(), tuple(array)))
            case jvm.Object(jvm.ClassName("java.lang.String")):
                rand_length = rand.randint(0, 10000)
                random_string = "".join(random.choices(string.ascii_letters + string.digits, k=rand_length))
                input.append(jpamb.case.String(random_string))
            case jvm.Object(jvm.ClassName("jpamb.utils.Smith")):
                rand_length = rand.randint(0, 10000)
                random_bits = "".join(rand.choice("01") for _ in range(rand_length))
                input.append(jpamb.case.Smith(random_bits))

            case a:
                raise NotImplementedError(
                    f"Don't know how to create random values for {a}"
                )

    return jpamb.case.Input(tuple(input))


def expand_dictionary(
    dictionary: dict[type, list],
    integer_operations: tuple[IntegerOperation, ...] = (),
) -> dict[type, list]:
    """Post-processes a converted dictionary by adding +/-1 neighbors and derived arithmetic values."""
    if int not in dictionary:
        return dictionary

    base_ints = list(dictionary[int])
    expanded = list(base_ints)

    for v in base_ints:
        for neighbor in (v - 1, v + 1):
            if neighbor not in expanded:
                expanded.append(neighbor)

    if integer_operations:
        for val in islice(arithmetic_seed_values(base_ints, integer_operations), 32):
            if val not in expanded:
                expanded.append(val)

    dictionary[int] = expanded
    return dictionary


def get_method_dictionary(
    methodid: jvm.AbsMethodID,
    suite: jpamb.Suite,
    integer_operations: tuple[IntegerOperation, ...] = (),
) -> dict[type, list]:
    """Extracts and expands the dictionary for a method."""
    raw_literals = get_literals_in_method(methodid, suite)
    dictionary = convert_literals(raw_literals)
    return expand_dictionary(dictionary, integer_operations)


def smith_outcomes(bc: jpamb.Bytecode, methodid: jvm.AbsMethodID) -> dict[str, list[AbstractSmith]]:
    if tuple(methodid.extension.params).count(SMITH_TYPE) != 1:
        return {}

    try:
        return abstract_analysis_results(bc, methodid)
    except (NotImplementedError, AssertionError):
        # Static analysis supports a subset of the dynamic interpreter's inputs.
        return {}


def static_smith_seeds(results: dict[str, list[AbstractSmith]]) -> list[str]:
    """Sample concrete bit strings from the Smith states for each outcome."""
    seeds: set[str] = set()
    for states in results.values():
        for smith in states:
            if smith.is_bot:
                continue
            lengths = {
                max(0, smith.length.min or 0),
                smith.length.max,
                len(smith.pattern),
                smith.cursor.min,
                smith.cursor.max,
            }
            for length in lengths:
                if length is None or not 0 <= length <= MAX_SMITH_SEED_LENGTH or length not in smith.length:
                    continue
                pattern = smith.pattern[:length].ljust(length, "?")
                seeds.update(pattern.replace("?", bit) for bit in "01")
    return sorted(seeds, key=lambda bits: (len(bits), bits))


def analysis_inputs(
    methodid: jvm.AbsMethodID,
    suite: jpamb.Suite,
    structure: list = (),
    dictionary: dict = {},
    smith_results: dict[str, list[AbstractSmith]] = {},
    integer_operations: tuple[IntegerOperation, ...] = (),
):
    if not methodid.extension.params:
        yield jpamb.case.Input(())
        return

    rand = random.Random(0)
    for _ in range(10):
        yield fuzz_input(rand, methodid)

    if dictionary:
        dictionary_seeds = iter(generate_inputs_from_dict(methodid, suite, literals=dictionary))
        template = next(dictionary_seeds, None)
        if template is not None:
            yield template
            yield from arithmetic_inputs(template, dictionary.get(int, []), integer_operations)
        yield from dictionary_seeds

    smith_idx = next(
        (
            i
            for i, p in enumerate(methodid.extension.params)
            if isinstance(p, jvm.Object) and "Smith" in str(p.name)
        ),
        None,
    )
    if smith_idx is not None:
        guided = static_smith_seeds(smith_results)
        structured = generate_bitstring_inputs(structure, dictionary) if structure else []
        for bits in dict.fromkeys([*guided, *structured]):
            args = []
            for i, p in enumerate(methodid.extension.params):
                if i == smith_idx:
                    args.append(jpamb.case.Smith(bits))
                else:
                    match p:
                        case jvm.Int():
                            args.append(jpamb.case.Int(0))
                        case jvm.Boolean():
                            args.append(jpamb.case.Boolean(False))
                        case jvm.Object():
                            args.append(jpamb.case.String(""))
                        case jvm.Array(contains=ct):
                            args.append(jpamb.case.Array(ct, ()))
                        case _:
                            args.append(jpamb.case.Int(0))
            yield jpamb.case.Input(tuple(args))


def init_context(
    methodid: jvm.AbsMethodID,
    suite: jpamb.Suite,
    bc: jpamb.Bytecode,
) -> FuzzContext:
    """Initializes and returns the fuzzing context, applying any environment configuration overrides."""
    use_dictionary = not _env_disabled("DISABLE_DICTIONARY")
    use_syntactic_structure = not _env_disabled("DISABLE_SYNTACTIC_STRUCTURE")
    use_static_seeds = not _env_disabled("DISABLE_STATIC_SEEDS")
    use_dynamic_structure = not _env_disabled("DISABLE_DYNAMIC_STRUCTURE")

    integer_operations = get_integer_operations(methodid, suite) if use_dictionary else ()
    dictionary = get_method_dictionary(methodid, suite, integer_operations) if use_dictionary else {}
    structure = list(get_bitstring_structure(methodid, suite)) if use_syntactic_structure else []
    smith_results = smith_outcomes(bc, methodid) if use_static_seeds else {}

    initial_seeds = list(
        analysis_inputs(
            methodid,
            suite,
            structure,
            dictionary,
            smith_results,
            integer_operations,
        )
    )

    return FuzzContext(
        dictionary=dictionary,
        structure=structure,
        smith_results=smith_results,
        integer_operations=integer_operations,
        initial_seeds=initial_seeds,
        use_dynamic_structure=use_dynamic_structure,
    )
