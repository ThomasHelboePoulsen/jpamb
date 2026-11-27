import random
import string

import jpamb
import jvm

from helpers.dynamic_java_literals import generate_inputs_from_dict
from interpreter import initial, interpret, step
from helpers.state_snapshot import state_snapshot


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


def analysis_inputs(methodid, suite):
    if not methodid.extension.params:
        yield jpamb.case.Input(())
        return

    rand = random.Random(0)
    for _ in range(10):
        yield fuzz_input(rand, methodid)
    yield from generate_inputs_from_dict(methodid, suite)


def analyse():
    """The dynamic analysis, dumb fuzzer + dictionary."""
    methodid = jpamb.getmethodid(
        "dynamic",
        "1.0",
        "Bit Diddlers",
        ["dynamic", "python"],
        for_science=True,
    )

    suite, eff = jpamb.setup()
    bc = jpamb.Bytecode(suite, eff, {})

    MAX_STEPS = 2000

    behaviors = set()
    for input in analysis_inputs(methodid, suite):
        state = initial(bc, methodid, input)
        seen_states = set()
        for x in range(MAX_STEPS):
            pc, state = step(bc, state)
            if isinstance(state, str):
                behaviors.add(state)
                break
            snapshot = state_snapshot(state)
            if snapshot in seen_states:
                behaviors.add("*")
                break
            seen_states.add(snapshot)

    for query in jpamb.QUERIES:
        if query in behaviors:
            if query == "*":
                print(f"{query};timeout")
            else:
                print(f"{query};found")
        else:
            print(f"{query};not-found")
