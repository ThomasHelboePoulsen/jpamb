import random
from helpers.bitstring_input_generation import (
    crop,
    int_to_bits,
    bits_to_int,
    replace_bits,
    generate_inputs,
    mutate_input,
)


def test_crop():
    assert crop(5, 3) == 5 % 8  # 5
    assert crop(10, 3) == 10 % 8  # 2
    assert crop(-1, 4) == 15  # 1111 in two's complement
    assert crop("11010", 3) == "010"
    assert crop("1", 3) == "001"


def test_int_to_bits_and_back():
    assert int_to_bits(5, 4) == "0101"
    assert bits_to_int("0101") == 5
    assert int_to_bits(-1, 4) == "1111"
    assert bits_to_int("1111") == 15


def test_replace_bits():
    assert replace_bits("00000", 1, 3, "111") == "01110"
    assert replace_bits("00", 2, 3, "11") == "0011"


def test_generate_inputs():
    structure = [("integer", 0, 3), ("boolean", 4, 4)]
    dictionary = {int: [42]}
    seeds = generate_inputs(structure, dictionary)

    assert len(seeds) > 0
    # Every generated seed should be at least max_index + 2 long
    for s in seeds:
        assert isinstance(s, str)


def test_mutate_input():
    structure = [("integer", 0, 3)]
    rand = random.Random(42)
    original = "000000"
    mutated = mutate_input(original, structure, dictionary={int: [10]}, rand=rand)
    assert isinstance(mutated, str)
    assert len(mutated) >= 2
