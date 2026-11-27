import random
import string

import jpamb
import jvm

from helpers.dynamic_java_literals import convert_literals, get_literals_in_method
from interpreter import initial, step


def fuzz_input(rand: random.Random, methodid: jvm.AbsMethodID, literals: dict[type, list]) -> jpamb.case.Input:
    """Use a pool of n distinct values with probability n / (n + 9)."""
    min_int, max_int = -(1 << 31), (1 << 31) - 1
    int_literals = [
        value for value in dict.fromkeys(literals.get(int, []))
        if min_int <= value <= max_int
    ]
    bool_literals = list(dict.fromkeys(literals.get(bool, [])))
    string_literals = list(dict.fromkeys(literals.get(str, [])))
    char_literals = [
        value for value in string_literals
        if len(value) == 1 and ord(value) <= 0xFFFF
    ]

    def choose_value(pool, random_value):
        dictionary_probability = 0.5
        if pool and rand.random() < dictionary_probability:
            return rand.choice(pool)
        return random_value()

    def fuzz_int():
        return choose_value(int_literals, lambda: rand.randint(min_int, max_int))

    def random_string():
        length = rand.randint(0, 10000)
        return "".join(rand.choices(string.ascii_letters + string.digits, k=length))

    input = []
    for p in methodid.extension.params:
        match p:
            case jvm.Int():
                input.append(jpamb.case.Int(fuzz_int()))
            case jvm.Boolean():
                value = choose_value(bool_literals, lambda: bool(rand.randint(0, 1)))
                input.append(jpamb.case.Boolean(value))
            case jvm.Array(contains=jvm.Int()):
                rand_upperbound = rand.randint(1, 10000)
                rand_length = rand.randint(0, rand_upperbound)
                array = []
                for i in range(rand_length):
                    rand_val = fuzz_int()
                    array.append(rand_val)
                input.append(jpamb.case.Array(jvm.Int(), tuple(array)))
            case jvm.Array(contains=jvm.Char()):
                rand_upperbound = rand.randint(1, 10000)
                rand_length = rand.randint(0, rand_upperbound)
                array = []
                for i in range(rand_length):
                    value = choose_value(char_literals, lambda: chr(rand.randint(32, 126)))
                    array.append(value)
                input.append(jpamb.case.Array(jvm.Char(), tuple(array)))
            case jvm.Object(jvm.ClassName("java.lang.String")):
                value = choose_value(string_literals, random_string)
                input.append(jpamb.case.String(value))
            case a:
                raise NotImplementedError(
                    f"Don't know how to create random values for {a}"
                )

    return jpamb.case.Input(tuple(input))


def analyse():
    """The dynamic analysis, e.g. in this case a (dumb) fuzzer."""
    methodid = jpamb.getmethodid(
        "dynamic_dict",
        "1.0",
        "Bit Diddlers",
        ["dynamic", "python"],
        for_science=True,
    )

    suite, eff = jpamb.setup()
    bc = jpamb.Bytecode(suite, eff, {})

    raw_literals = get_literals_in_method(methodid, suite)
    literals = convert_literals(raw_literals)
    MAX_STEPS = 200

    rand = random.Random(0)
    behaviors = set()

    for i in range(10):
        input = fuzz_input(rand, methodid, literals)
        state = initial(bc, methodid, input)

        for x in range(MAX_STEPS):
            _, state = step(bc, state)
            if isinstance(state, str):
                behaviors.add(state)
                break

    for query in jpamb.QUERIES:
        if query in behaviors:
            if query == "*":
                print(f"{query};timeout")
            else:
                print(f"{query};found")
        else:
            print(f"{query};not-found")
