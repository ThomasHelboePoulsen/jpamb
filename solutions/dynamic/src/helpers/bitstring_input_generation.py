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



def generate_inputs(
    structure: Sequence[Tuple[str, int, int]],
    dictionary: dict | Sequence[int] | None = None,
) -> list[str]:
    """Generates an initial seed pool of bitstrings using the bit structure and optional literal dictionary.

    These seeds populate the initial corpus before the fuzzing loop starts.
    """
    max_index = max(end for _, _, end in structure) if structure else 0
    required_length = max_index + 2

    results: set[str] = set()

    
    results.update(["", "0", "1", "00", "01", "10", "11"])

    
    all_zeros = "0" * required_length
    all_ones = "1" * required_length
    alternating = ("01" * math.ceil(required_length / 2))[:required_length]
    results.update([all_zeros, all_ones, alternating])

    # runway to allow loops to populate the dynamic recorded reading structure.
    for runway_len in (20, 50, 100,250,500,100):
        results.add("0" * runway_len)
        results.add("1" * runway_len)
    for zeros_count in (1, 2, 3, 4, 5, 8, 16):
        results.add(("0" * zeros_count) + "1" + ("0" * 10))

    
    dict_ints: list[int] = []
    if dictionary:
        raw_ints = dictionary.get(int, []) if isinstance(dictionary, dict) else dictionary
        for v in raw_ints:
            dict_ints.extend([v, v - 1, v + 1])

   
    for field_type, start, end in structure:
        width = (end - start) + 1

        if field_type == "boolean":
            results.add(replace_bits(all_zeros, start, end, "1"))
            results.add(replace_bits(all_ones, start, end, "0"))

        elif field_type == "integer":
            max_val = crop(-1, width)
            boundary_values = {0, 1, 2, 5, -1, -2, max_val}
            for v in dict_ints:
                boundary_values.add(v)

            for val in boundary_values:
                bit_pattern = int_to_bits(val, width)
                results.add(replace_bits(all_zeros, start, end, bit_pattern))
                results.add(replace_bits(all_ones, start, end, bit_pattern))

    return sorted(results, key=lambda s: (len(s), s))


def mutate_input(
    bitstring: str,
    structure: Sequence[Tuple[str, int, int]],
    dictionary: dict | Sequence[int] | None = None,
    rand=None,
) -> str:
    if rand is None:
        rand = random
    max_index = max(end for _, _, end in structure) if structure else 0
    min_length = max_index + 2
    if not bitstring or len(bitstring) < min_length:
        bitstring = bitstring + ("0" * (min_length - len(bitstring)))
    bits = list(bitstring)
    if structure and rand.random() < 0.7:
        field_type, start, end = rand.choice(structure)
        width = (end - start) + 1
        while len(bits) <= end:
            bits.append("0")

        if field_type == "boolean":
            
            bits[start] = "1" if bits[start] == "0" else "0"
            return "".join(bits)

        elif field_type == "integer":
            action = rand.choice(["target_value", "arithmetic", "bitflip"])
            current_int = bits_to_int("".join(bits[start : end + 1]))

            if action == "target_value":
                max_val = crop(-1, width)
                candidates = [0, 1, 2, 5, -1, -2, max_val]
                if dictionary:
                    raw_ints = dictionary.get(int, []) if isinstance(dictionary, dict) else dictionary
                    for v in raw_ints:
                        candidates.extend([v, v - 1, v + 1])
                new_val = rand.choice(candidates)
                new_bits = int_to_bits(new_val, width)
                bits[start : end + 1] = list(new_bits)

            elif action == "arithmetic":
                delta = rand.choice([-1, 1, -2, 2])
                new_val = crop(current_int + delta, width)
                new_bits = int_to_bits(new_val, width)
                bits[start : end + 1] = list(new_bits)

            else:  # bitflip within integer range
                flip_idx = rand.randint(start, end)
                bits[flip_idx] = "1" if bits[flip_idx] == "0" else "0"

            return "".join(bits)

    # basic mutations
    choice = rand.choice(["flip", "truncate", "append"])

    if choice == "flip" and bits:
        idx = rand.randrange(len(bits))
        bits[idx] = "1" if bits[idx] == "0" else "0"

    elif choice == "truncate" and len(bits) > 1:
       
        cut = rand.randint(1, len(bits) - 1)
        bits = bits[:cut]

    else:  
        bits.extend(rand.choice("01") for _ in range(rand.randint(1, 4)))

    return "".join(bits)
