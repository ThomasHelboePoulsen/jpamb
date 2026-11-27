"""Helpers for bitstring generation and mutation guided by syntactic bit structure."""

import math
import random
from typing import Sequence, Tuple




def crop(value: int | str, width: int):
    """Crops an integer or binary string to the rightmost 'width' bits (applying the modulo)."""
    if isinstance(value, str):
        return value[-width:] if len(value) >= width else value.zfill(width)
    return value % (1 << width)


def int_to_bits(value: int, width: int) -> str:
    """Converts a number into a binary string of exact width.
    
    Handles both positive and negative integers using two's complement:
      int_to_bits(5, width=4)  -> "0101"
      int_to_bits(-1, width=4) -> "1111"
    """
    # Crop to the rightmost 'width' bits
    val = crop(value, width)
    binary_string = bin(val)[2:]
    return binary_string.zfill(width)


def bits_to_int(bits: str) -> int:
    """Converts a binary string back into a standard integer.
    """
    if not bits:
        return 0
    return int(bits, 2)


def replace_bits(bitstring: str, start: int, end: int, new_bits: str) -> str:
    """Replaces a slice of a bitstring between start and end with new_bits.
    
    If the string is too short, it appends zeros to the right first.
    """
    
    if len(bitstring) <= end:
        missing_zeros = (end + 1) - len(bitstring)
        bitstring = bitstring + ("0" * missing_zeros)

    
    before = bitstring[:start]
    after = bitstring[end + 1 :]
    return before + new_bits + after



def generate_bitstring_inputs(
    structure: Sequence[Tuple[str, int, int]],
    dictionary: dict | Sequence[int] | None = None,
    base_seed: str | None = None,
) -> list[str]:
    """Generates bitstring inputs for the given structure and dictionary.

    If `base_seed` is provided, alters `base_seed` directly at each field in `structure`.
    Otherwise, creates an initial seed pool using all-zeros, all-ones, and alternating templates.
    """
    max_index = max(end for _, _, end in structure) if structure else 0
    required_length = max_index + 2

    results: set[str] = set()

    if base_seed is not None:
        templates = [base_seed]
    else:
        results.update(["", "0", "1", "00", "01", "10", "11"])
        all_zeros = "0" * required_length
        all_ones = "1" * required_length
        alternating = ("01" * math.ceil(required_length / 2))[:required_length]
        results.update([all_zeros, all_ones, alternating])
        templates = [all_zeros, all_ones]

    dict_ints = (
        dictionary.get(int, []) if isinstance(dictionary, dict) else list(dictionary)
    ) if dictionary else []

    for field_type, start, end in structure:
        width = (end - start) + 1

        match field_type:
            case "boolean":
                for template in templates:
                    results.add(replace_bits(template, start, end, "1"))
                    results.add(replace_bits(template, start, end, "0"))

            case "integer":
                max_val = crop(-1, width)
                boundary_values = {0, 1, 2, 5, -1, -2, max_val, *dict_ints}

                for val in boundary_values:
                    bit_pattern = int_to_bits(val, width)
                    for template in templates:
                        results.add(replace_bits(template, start, end, bit_pattern))

    return sorted(results, key=lambda s: (len(s), s))


def mutate_boolean_struct(bits: list[str], start: int) -> None:
    """Mutates a boolean field in-place by flipping the bit at start."""
    bits[start] = "1" if bits[start] == "0" else "0"


def mutate_integer_struct(
    bits: list[str],
    start: int,
    end: int,
    dictionary: dict | Sequence[int] | None = None,
    rand=random,
) -> None:
    """Mutates an integer field in-place using target values, arithmetic, or bitflips."""
    width = (end - start) + 1
    action = rand.choice(["target_value", "arithmetic", "bitflip"])
    current_int = bits_to_int("".join(bits[start : end + 1]))

    match action:
        case "target_value":
            max_val = crop(-1, width)
            raw_ints = []
            if dictionary:
                raw_ints = dictionary.get(int, []) if isinstance(dictionary, dict) else dictionary
            
           
            if raw_ints and rand.random() < 0.75:
                new_val = rand.choice(raw_ints)
            else:
                boundary = [0, 1, 2, -1, -2, max_val]
                if rand.random() < 0.4:
                    new_val = rand.choice(boundary)
                else:
                    new_val = rand.randint(0, max_val)

            new_bits = int_to_bits(new_val, width)
            bits[start : end + 1] = list(new_bits)

        case "arithmetic":
            delta = rand.choice([-1, 1, -2, 2])
            new_val = crop(current_int + delta, width)
            new_bits = int_to_bits(new_val, width)
            bits[start : end + 1] = list(new_bits)

        case "bitflip":
            flip_idx = rand.randint(start, end)
            bits[flip_idx] = "1" if bits[flip_idx] == "0" else "0"


def mutate_struct(
    bits: list[str],
    structure: Sequence[Tuple[str, int, int]],
    dictionary: dict | Sequence[int] | None = None,
    rand=random,
) -> None:
    """Mutates structure fields using chained geometric expansion and occasional boundary probes."""
    if rand.random() < 0.02: # check boundaries
        fill_char = rand.choice(["1", "0"])
        for _, start, end in structure:
            bits[start : end + 1] = [fill_char] * (end - start + 1)
        return

    shuffled = list(structure)
    rand.shuffle(shuffled)
    fields_to_mutate = [shuffled[0]]
    # prevent one mutation overwriting another
    occupied_indices = set(range(shuffled[0][1], shuffled[0][2] + 1))

    for field in shuffled[1:]:
        if rand.random() < 0.35:
            _, start, end = field
            field_indices = set(range(start, end + 1))
            if not (occupied_indices & field_indices):
                fields_to_mutate.append(field)
                occupied_indices.update(field_indices)
        else:
            break

    for field_type, start, end in fields_to_mutate:
        match field_type:
            case "boolean":
                mutate_boolean_struct(bits, start)
            case "integer":
                mutate_integer_struct(bits, start, end, dictionary, rand)


def mutate_input(
    bitstring: str,
    structure: Sequence[Tuple[str, int, int]],
    dictionary: dict | Sequence[int] | None = None,
    rand=None,
) -> str:
    if rand is None:
        rand = random
    bits = list(bitstring)

    if structure:
        max_length = max(end for _, _, end in structure) + 1
        if len(bits) < max_length:
            bits.extend("0" * (max_length - len(bits)))

    if structure and rand.random() < 0.7:
        mutate_struct(bits, structure, dictionary, rand)
        return "".join(bits)

    # Basic mutations without truncate (capping append length to avoid bloat)
    choice = rand.choice(["flip", "append"]) if (bits and len(bits) < 128) else ("flip" if bits else "append")
    match choice:
        case "flip":
            idx = rand.randrange(len(bits))
            bits[idx] = "1" if bits[idx] == "0" else "0"
        case "append":
            bits.extend(rand.choice("01") for _ in range(rand.randint(1, 4)))

    return "".join(bits)
