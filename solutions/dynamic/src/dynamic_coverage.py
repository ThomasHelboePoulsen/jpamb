# dynamic analysis using coverage based fuzzing.
import random
import sys
import string
from abstractions import AbstractSmith
from bitstring_structure import get_bitstring_structure
from helpers.bitstring_input_generation import generate_inputs, mutate_input as mutate_bitstring
import jpamb
import jvm
import jvm.state as jvmc

from dynamic_java_literals import (
    convert_literals,
    generate_inputs_from_dict,
    get_literals_in_method,
)
from integer_input_generation import (
    IntegerOperation,
    arithmetic_inputs,
    get_integer_operations,
    mutate_integer,
)
from state_snapshot import ExecutionSnapshots
from static import SMITH_TYPE, abstract_analysis_results

MAX_SMITH_SEED_LENGTH = 10_000


def signed_int(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - 2**32 if value >= 2**31 else value


def binary(op, v1: int, v2: int) -> int | str:
    match op:
        case jvm.BinaryOpr.Div:
            try:
                return v1 // v2
            except ZeroDivisionError:
                return "divide by zero"
        
        case jvm.BinaryOpr.Add:
            return signed_int(v1 + v2)
        case jvm.BinaryOpr.Sub:
            return v1 - v2
        case jvm.BinaryOpr.Mul:
            return v1 * v2
        case jvm.BinaryOpr.Rem:
            try:
                return v1 % v2
            except ZeroDivisionError:
                return "divide by zero"
        
        case a:
            raise NotImplementedError(f"Unhandled binary {op!r}")


def compare(op, v1: int, v2: int) -> bool:
    match op:
        case jvm.CmpOpr.Eq:
            return v1 == v2
        case jvm.CmpOpr.Ne:
            return v1 != v2
        case jvm.CmpOpr.Gt:
            return v1 > v2
        case jvm.CmpOpr.Ge:
            return v1 >= v2
        case jvm.CmpOpr.Lt:
            return v1 < v2
        case jvm.CmpOpr.Le:
            return v1 <= v2
        case _:
            raise NotImplementedError(f"Unhandled comparation {op!r}")


def draw_bit(state: jvmc.State, ref: jvmc.StackReference) -> bool:
    smith = state.heap[ref]
    assert isinstance(smith, jvmc.HeapObject)
    bits_field = jvm.FieldID(
        "bits", jvm.Object(jvm.ClassName("java.lang.String"))
    )
    index_field = jvm.FieldID("index", jvm.Int())
    bits_ref = smith.fields[bits_field]
    index = smith.fields[index_field]
    assert isinstance(bits_ref, jvmc.StackReference)
    assert isinstance(index, jvmc.StackInt)
    bits = state.heap[bits_ref]
    assert isinstance(bits, jvmc.HeapString)
    if index.value >= len(bits.content):
        return False

    if hasattr(state, "recorded_reads"):
        state.recorded_reads.append(("boolean", index.value, index.value))

    smith.fields[index_field] = jvmc.StackInt(index.value + 1)
    return bits.content[index.value] != "0"


def draw_int(state: jvmc.State, ref: jvmc.StackReference, count: int) -> int | str:
    if count < 0:
        return "illegal argument"
    smith = state.heap[ref]
    bits_field = jvm.FieldID("bits", jvm.Object(jvm.ClassName("java.lang.String")))
    index_field = jvm.FieldID("index", jvm.Int())
    bits_ref = smith.fields[bits_field]
    index = smith.fields[index_field].value
    bits = state.heap[bits_ref].content

    if hasattr(state, "recorded_reads"):
        state.recorded_reads.append(("integer", index, index + count - 1))

    end = index + count
    cursor = min(end, len(bits))
    smith.fields[index_field] = jvmc.StackInt(cursor)

    # Only the last 32 bits contribute, even when the draw pads with zeros.
    suffix = bits[max(index, end - 32):cursor]
    if not suffix:
        return 0
    return signed_int(int(suffix, 2) << (end - cursor))


def step(bc: jpamb.Bytecode, state: jvmc.State) -> tuple[jvmc.PC, jvmc.State | str]:
    assert isinstance(state, jvmc.State), f"expected state but got {state}"
    frame = state.frames.peek()
    pc = frame.pc
    opr = bc[pc]
    output = state
    #print(f"Stepping {pc}:\n > {opr}", file=sys.stderr)
    match opr:
        case jvm.Push(type=t, value=v):
            
            if t is jvm.Int():
                frame.stack.push(jvmc.StackInt(v))
            elif t is jvm.Reference():
                frame.stack.push(jvmc.StackReference(v))
            elif t is jvm.Boolean():
                frame.stack.push(jvmc.StackInt(1 if v else 0))
            elif t is jvm.Char():
                frame.stack.push(jvmc.StackInt(ord(v)))
            elif t is jvm.Short():
                frame.stack.push(jvmc.StackInt(v))
            elif isinstance(t, jvm.Object) and isinstance(v, str):
                ref = state.heap.new(jvmc.HeapString(v))
                frame.stack.push(ref)

            else:
                raise NotImplementedError("Error: " + opr.help())
            frame.pc += 1

        case jvm.Binary(type=jvm.Int(), operant=op):
            v2, v1 = frame.stack.pop(), frame.stack.pop()
            assert isinstance(v1, jvmc.StackInt), f"expected int, but got {v1}"
            assert isinstance(v2, jvmc.StackInt), f"expected int, but got {v2}"

            value = binary(op, v1.value, v2.value)

            if isinstance(value, str):
                output = value
            else:
                frame.stack.push(jvmc.StackInt(value))
                frame.pc += 1

        case jvm.Return(type=None):
                    state.frames.pop()
                    if state.frames:
                        frame = state.frames.peek()
                        frame.pc += 1
                    else:
                        output = "ok"
        case jvm.Return(type=return_type):
            v1 = frame.stack.pop()
            state.frames.pop()
            if state.frames:
                frame = state.frames.peek()
                frame.stack.push(v1)
                frame.pc += 1
            else:
                output = "ok"
                
        

        case jvm.Get(static=True, field=field):
            # Hack - Only handle the assertion case
            assert field.extension.name == "$assertionsDisabled"

            # Hack - Assuming assertions are never disabled
            frame.stack.push(jvmc.StackInt(0))
            frame.pc += 1

        case jvm.New(classname=jvm.ClassName("java.lang.AssertionError")):
            # Hack -- if we create an assertion error, we probably also throw it.
            output = "assertion error"
            
        case jvm.Dup():
            v = frame.stack.pop()
            frame.stack.push(v)
            frame.stack.push(v)
            frame.pc += 1
            
        case jvm.Ifz(condition=op, target=target):
            value = frame.stack.pop()
            assert isinstance(value, jvmc.StackInt), f"expected int, but got {value}"

            if compare(op, value.value, 0):
                frame.pc %= target
            else:
                frame.pc += 1
        
        case jvm.If(condition=op, target=target):
            v2, v1 = frame.stack.pop(), frame.stack.pop()
            assert isinstance(v1, jvmc.StackInt), f"expected int, but got {v1}"
            assert isinstance(v2, jvmc.StackInt), f"expected int, but got {v2}"
            if compare(op, v1.value, v2.value):
                frame.pc %= target
            else:
                frame.pc += 1

        case jvm.NewArray(type=jvm.Int(), dim=dim):
            count =  frame.stack.pop()
            assert isinstance(count, jvmc.StackInt), f"expected int, but got {count}"
            assert count.value>=0, f"expected non negative array size, but got {count} "

            if count.value >= 10_000_000:
                output = "out of memory"
            else:  
                try:
                    ref = state.heap.new(jvmc.HeapArray(jvm.Int(), [0] * count.value))
                    frame.stack.push(ref)
                    frame.pc += 1
                except MemoryError:
                    output =  "out of memory"

        case jvm.ArrayStore(type=jvm.Int()):
            value, index, ref = frame.stack.pop(), frame.stack.pop(), frame.stack.pop()
            assert isinstance(value, jvmc.StackInt), f"expected int, but got {value}"
            assert isinstance(index, jvmc.StackInt), f"expected int, but got {index}"
            assert isinstance(ref, jvmc.StackReference), f"expected reference, but got {ref}"
            if ref.value == 0:
                output = "null pointer"
            else:
                array = state.heap[ref]
                if not 0 <= index.value < len(array.values):
                    output = "out of bounds"
                else:
                    array.values[index.value] = value.value
                    frame.pc += 1

        case jvm.ArrayLoad(type=t):
            index, ref = frame.stack.pop(), frame.stack.pop()
            assert isinstance(index, jvmc.StackInt), f"expected int, but got {index}"
            assert isinstance(ref, jvmc.StackReference), f"expected reference, but got {ref}"
            if ref.value == 0:
                output = "null pointer"
            else:
                array = state.heap[ref]
                assert isinstance(array, jvmc.HeapArray), f"expected array, but got {array}"
                assert isinstance(array.contains, type(t)), f"expected int array, but got {array.contains} AND {t}"
                if not 0 <= index.value < len(array.values):
                    output = "out of bounds"
                else:
                    value = array.values[index.value]
                    frame.stack.push(jvmc.StackInt(value))
                    frame.pc += 1

        case jvm.ArrayLength():
            ref = frame.stack.pop()
            assert isinstance(ref, jvmc.StackReference), f"expected reference, but got {ref}"
            if ref.value == 0:
                output = "null pointer"
            else:
                length = len(state.heap[ref].values)
                frame.stack.push(jvmc.StackInt(length))
                frame.pc += 1

        case jvm.Store(type=jvm.Reference(), index=i):
            ref = frame.stack.pop()
            assert isinstance(ref, jvmc.StackReference), f"expected reference, but got {ref}"
            frame.locals[i] = ref
            frame.pc += 1

        case jvm.Store(type=jvm.Int(), index=i):
            val = frame.stack.pop()
            assert isinstance(val, jvmc.StackInt), f"expected int, but got {val}"
            frame.locals[i] = val
            frame.pc += 1

        case jvm.Load(type=jvm.Int(), index=i):
            frame.stack.push(frame.locals[i])
            frame.pc += 1

        case jvm.Load(type=jvm.Reference(), index=i):
            frame.stack.push(frame.locals[i])
            frame.pc += 1

        case jvm.Incr(index=i, amount=amount):
            assert isinstance(i, int), f"expected int, but got {i}"
            assert isinstance(amount, int), f"expected int, but got {amount}"
            assert isinstance(frame.locals[i], jvmc.StackInt), f"expected int, but got {frame.locals[i]}"
            frame.locals[i] = jvmc.StackInt(amount + frame.locals[i].value)
            frame.pc += 1

        case jvm.Goto(target=target):
            frame.pc %= target


        case jvm.Cast(from_=jvm.Int(), to_=jvm.Short()):
            value = frame.stack.pop()
            assert isinstance(value, jvmc.StackInt), f"expected int, but got {value}"
            frame.stack.push(jvmc.StackInt(value.value & 0xFFFF))
            frame.pc += 1
        case jvm.InvokeStatic(
            method=jvm.AbsMethodID(
                classname=jvm.ClassName(cls_name), 
                extension=jvm.MethodID(
                    name=method_name, 
                    params=method_params, 
                    return_type=ret_type
                )
            ) as method_id
            ):
            parameter_count = len(method_params)
            args = []
            for i in range(parameter_count):
                args.append(frame.stack.pop())
            args.reverse() 

            method_obj = bc.getmethod(method_id)
            new_frame =create_method_frame(method_obj,args)
            state.frames.push(new_frame)

        case jvm.InvokeInterface(method=method):
            args = []
            for p in method.extension.params:
                v = frame.stack.pop()
                match p:
                    case jvm.Int():
                        assert isinstance(v, jvmc.StackInt), f"expected int, but got {v}"
                        args.append(v.value)
                    case jvm.Reference() | jvm.Object():
                        assert isinstance(v, jvmc.StackReference), (
                            f"expected reference, but got {v}"
                        )
                        args.append(v.value)
                    case a:
                        raise NotImplementedError(
                            f"Do not know how to handle parameter of type {a!r}"
                        )
            args.reverse()
            ref = frame.stack.pop()
            assert isinstance(ref, jvmc.StackReference), f"expected reference, but got {ref}"
            if ref.value == 0:
                output = "null pointer"
            else:
                if method.extension.name == "draw":
                    if not args:
                        assert isinstance(method.extension.return_type, jvm.Boolean)
                        value = draw_bit(state, ref)
                    else:
                        assert len(args) == 1
                        assert isinstance(method.extension.return_type, jvm.Int)
                        value = draw_int(state, ref, args[0])
                    if isinstance(value, str):
                        output = value
                    else:
                        frame.stack.push(
                            jvmc.StackInt(int(value))
                        )
                        frame.pc += 1
                else:
                    raise NotImplementedError(
                        f"Unsupported interface method: {method.extension.name}"
                    )

        case jvm.InvokeVirtual(method=method):
            args = []
            for p in method.extension.params:
                v = frame.stack.pop()
                match p:
                    case jvm.Int():
                        assert isinstance(v, jvmc.StackInt), f"expected int, but got {v}"
                        args.append(v.value)
                    case jvm.Reference() | jvm.Object():
                        assert isinstance(v, jvmc.StackReference), (
                            f"expected reference, but got {v}"
                        )
                        args.append(v.value)
                    case a:
                        raise NotImplementedError(
                            f"Do not know how to handle parameter of type {a!r}"
                        )
            args.reverse()
            ref = frame.stack.pop()
            assert isinstance(ref, jvmc.StackReference), f"expected reference, but got {ref}"
            if ref.value == 0:
                output = "null pointer"
            else:
                if ref.value == 0:
                    output = "null pointer"
                elif method.extension.name == "assert":
                    assert method.extension.params == [jvm.Boolean()]
                    assert method.extension.return_type is jvm.Void()
                    frame.pc += 1
                elif method.encode() == "java.lang.String.charAt:(I)C":
                    string = state.heap[ref]
                    assert isinstance(string, jvmc.HeapString)
                    encoded = string.content.encode("utf-16-le", errors="surrogatepass")
                    offset = args[0] * 2
                    if not 0 <= offset < len(encoded):
                        output = "out of bounds"
                    else:
                        code_unit = int.from_bytes(encoded[offset : offset + 2], "little")
                        frame.stack.push(jvmc.StackInt(code_unit))
                        frame.pc += 1
                elif method.extension.name == "equals":
                    assert len(method.extension.params) == 1
                    assert isinstance(method.extension.params[0], jvm.Object)
                    assert isinstance(method.extension.return_type, jvm.Boolean)

                    other = args[0]
                    left = state.heap[ref]
                    right = None if other == 0 else state.heap[jvmc.StackReference(other)]
                    frame.stack.push(jvmc.StackInt(1 if left == right else 0))
                    frame.pc += 1
                else:
                    raise NotImplementedError(
                        f"Unsupported virtual method: {method.extension.name}"
                    )

        case jvm.Negate(type = jvm.Int()):
            v = frame.stack.pop()
            assert isinstance(v,jvmc.StackInt)
            negv =  binary(jvm.BinaryOpr.Sub,0,v.value)
            frame.stack.push(jvmc.StackInt(negv))
            frame.pc+=1
        case jvm.Bitopr(type = jvm.Int(), operant = op):
                    match op:
                        case jvm.BitOpr.Shr:
                            v2, v1 = frame.stack.pop(), frame.stack.pop()
                            assert isinstance(v1,jvmc.StackInt)
                            assert isinstance(v2,jvmc.StackInt)
                            res = v1.value >> (v2.value & 0b11111)
                            frame.stack.push(jvmc.StackInt(res))
                            frame.pc += 1
                        case jvm.BitOpr.Shl:
                            v2, v1 = frame.stack.pop(), frame.stack.pop()
                            assert isinstance(v1,jvmc.StackInt)
                            assert isinstance(v2,jvmc.StackInt)
                            res = v1.value << (v2.value & 0b11111)
                            res &= 0xFFFFFFFF
                            if res >= 2**31:
                                res -= 2**32
                            frame.stack.push(jvmc.StackInt(res))
                            frame.pc += 1
                        case jvm.BitOpr.And:
                            v2, v1 = frame.stack.pop(), frame.stack.pop()
                            assert isinstance(v1,jvmc.StackInt)
                            assert isinstance(v2,jvmc.StackInt)
                            res = v1.value & v2.value
                            frame.stack.push(jvmc.StackInt(res))
                            frame.pc += 1
                        case jvm.BitOpr.Or:
                            v2, v1 = frame.stack.pop(), frame.stack.pop()
                            assert isinstance(v1,jvmc.StackInt)
                            assert isinstance(v2,jvmc.StackInt)
                            res = v1.value | v2.value
                            frame.stack.push(jvmc.StackInt(res))
                            frame.pc += 1
                        case jvm.BitOpr.Xor:
                            v2, v1 = frame.stack.pop(), frame.stack.pop()
                            assert isinstance(v1,jvmc.StackInt)
                            assert isinstance(v2,jvmc.StackInt)
                            res = v1.value ^ v2.value
                            frame.stack.push(jvmc.StackInt(res))
                            frame.pc += 1
                        case jvm.BitOpr.Ushr:
                            v2, v1 = frame.stack.pop(), frame.stack.pop()
                            assert isinstance(v1,jvmc.StackInt)
                            assert isinstance(v2,jvmc.StackInt)
                            # Shift a nonnegative 32-bit pattern so zeros enter on the left.
                            res = (v1.value & 0xFFFFFFFF) >> (v2.value & 0b11111)
                            # Java still returns a signed int, including for a shift of zero.
                            if res >= 2**31:
                                res -= 2**32
                            frame.stack.push(jvmc.StackInt(res))
                            frame.pc += 1
                        case _:
                            raise NotImplementedError(opr.help())
        
        
        
        case a:
            raise NotImplementedError(a.help())

    assert isinstance(output, (jvmc.State, str))

    return pc, output


def initial(bc: jpamb.Bytecode, methodid: jvm.AbsMethodID, input: jpamb.Input):
    frame = jvmc.Frame.from_method(bc.getmethod(methodid))
    state = jvmc.State(jvmc.Heap(), jvmc.CallStack.from_frames([frame]))
    for i, v in enumerate(input.values):
        # Convert arbitrary values into local values
        match v:
            case jpamb.case.Boolean(value):
                frame.locals[i] = jvmc.StackInt(1 if value else 0)
            case jpamb.case.Int(value):
                frame.locals[i] = jvmc.StackInt(value)
            case jpamb.case.Array(contains=type, values=values):
                match type:
                    case jvm.Char():
                        ref = state.heap.new(
                            jvmc.HeapArray(type, [ord(a) for a in values])
                        )
                    case jvm.Int():
                        ref = state.heap.new(jvmc.HeapArray(type, [a for a in values]))
                frame.locals[i] = ref
            case jpamb.case.String(value=value):
                ref = state.heap.new(jvmc.HeapString(value))
                frame.locals[i] = ref
            case jpamb.case.Smith(value=value):
                stringField = jvm.FieldID(
                    "bits", jvm.Object(jvm.ClassName("java.lang.String"))
                )
                indexField = jvm.FieldID("index", jvm.Int())
                heapSt  = state.heap.new(jvmc.HeapString(value))
                heapOb= jvmc.HeapObject(jvm.ClassName("jpamb.utils.Smith"), {stringField: heapSt, indexField:jvmc.StackInt(0)})
                ref = state.heap.new(heapOb)
                frame.locals[i] = ref
            case a:
                raise NotImplementedError(
                    f"Do not know how to convert values of type {a!r} to a local value"
                )

    return state



def create_method_frame(method_obj, args):
    new_frame = jvmc.Frame.from_method(method_obj)
    assert not new_frame is None 
    for i, arg in enumerate(args):
        new_frame.locals[i] = arg
    return new_frame

def interpret():
    """The entry point for the interpreter"""

    methodid, input, max_steps = jpamb.getcase(
        "dynamic",
        "1.0",
        "Bit Diddlers",
        ["dynamic", "python"],
        for_science=True,
    )

    suite, eff = jpamb.setup()
    bc = jpamb.Bytecode(suite, eff, {})

    state = initial(bc, methodid, input)

    last = jpamb.emit_init(state)

    for x in range(max_steps):
        pc, state = step(bc, state)
        last = jpamb.emit_step(last, pc, state)

        if isinstance(state, str):
            break


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
                rand_length = rand.randint(0,rand_upperbound)
                array = []
                for i in range(rand_length):
                    rand_val = rand.randint(-(1 << 31), 1 << 31)
                    array.append(rand_val)
                input.append(jpamb.case.Array(jvm.Int(), tuple(array)))
            case jvm.Array(contains=jvm.Char()):
                rand_upperbound = rand.randint(1, 10000)
                rand_length = rand.randint(0,rand_upperbound)
                array = []
                for i in range(rand_length):
                    random_int = rand.randint(32, 126)
                    rand_char = chr(random_int)
                    array.append(rand_char)
                input.append(jpamb.case.Array(jvm.Char(), tuple(array)))
            case jvm.Object(jvm.ClassName("java.lang.String")):
                rand_length = rand.randint(0, 10000)
                random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=rand_length))
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


def get_method_dictionary(methodid, suite) -> dict[type, list]:
    """extracts dictionary for method"""
    raw_literals = get_literals_in_method(methodid, suite)
    return convert_literals(raw_literals)


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
    methodid, suite, *, smith_results=None, integer_operations: tuple[IntegerOperation, ...] = ()
):
    if not methodid.extension.params:
        yield jpamb.case.Input(())
        return

    rand = random.Random(0)
    for _ in range(10):
        yield fuzz_input(rand, methodid)

    dictionary = get_method_dictionary(methodid, suite)
    dictionary_seeds = iter(generate_inputs_from_dict(methodid, suite))
    template = next(dictionary_seeds, None)
    if template is not None:
        yield template
        yield from arithmetic_inputs(template, dictionary.get(int, []), integer_operations)
    yield from dictionary_seeds

    bitstring_structure = get_bitstring_structure(methodid, suite)

    smith_idx = next( #find smith 
        (
            i
            for i, p in enumerate(methodid.extension.params)
            if isinstance(p, jvm.Object) and "Smith" in str(p.name)
        ),
        None,
    )
    if smith_idx is not None:
        guided = static_smith_seeds(smith_results or {})
        structured = generate_inputs(bitstring_structure, dictionary)
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


def mutate_input(
    seed: jpamb.case.Input,
    structure,
    dictionary,
    *,
    target: AbstractSmith | None = None,
    integer_operations: tuple[IntegerOperation, ...] = (),
) -> jpamb.case.Input:
    
    new_values = []
    for val in seed.values:
        match val:
            case jpamb.case.Smith(bits):
                new_bits = mutate_bitstring(bits, structure, dictionary)
                if target is not None:
                    lower = max(0, target.length.min or 0)
                    upper = min(
                        MAX_SMITH_SEED_LENGTH,
                        target.length.max if target.length.max is not None else MAX_SMITH_SEED_LENGTH,
                    )
                    preferred = random.choice((len(new_bits), len(target.pattern), lower))
                    length = min(max(preferred, lower), upper)
                    new_bits = new_bits[:length] + "".join(
                        random.choice("01") for _ in range(length - len(new_bits))
                    )
                    new_bits = "".join(
                        bit if fixed == "?" else fixed
                        for bit, fixed in zip(new_bits, target.pattern)
                    ) + new_bits[len(target.pattern):]
                new_values.append(jpamb.case.Smith(new_bits))
            case jpamb.case.Int(num):
                new_values.append(jpamb.case.Int(mutate_integer(num, integer_operations)))
            case jpamb.case.Boolean(b):
                new_values.append(jpamb.case.Boolean(not b))
            case jpamb.case.Array(contains=ct, values=arr_vals):
                vals_list = list(arr_vals)
                choice = random.choice(["extend", "shorten", "modify", "keep"])
                match choice:
                    case "extend" if len(vals_list) < 20:
                        if ct == jvm.Char():
                            cand = random.choice(string.ascii_letters)
                        else:
                            cand = random.choice(dictionary.get(int, [0, 1])) if dictionary else 0
                        vals_list.append(cand)
                    case "shorten" if vals_list:
                        vals_list.pop()
                    case "modify" if vals_list:
                        idx = random.randrange(len(vals_list))
                        if ct == jvm.Char():
                            vals_list[idx] = random.choice(string.ascii_letters)
                        elif isinstance(vals_list[idx], int):
                            vals_list[idx] = mutate_integer(vals_list[idx], integer_operations)
                    case _:
                        pass  
                new_values.append(jpamb.case.Array(ct, tuple(vals_list)))
            case other:
                new_values.append(other)
    return jpamb.case.Input(tuple(new_values))
    
    
    
    



def loop_is_independent_of_changed_locals(
    bc: jpamb.Bytecode,
    loop_path: list[jvmc.PC],
    previous_locals: tuple,
    current_locals: tuple,
) -> bool:
    changed_local_indices = set()
    for index, (previous, current) in enumerate(zip(previous_locals, current_locals)):
        if previous == current:
            continue
        if not (isinstance(previous, jvmc.StackInt) and isinstance(current, jvmc.StackInt)):
            return False
        changed_local_indices.add(index)

    for pc in loop_path:
        instruction = bc[pc]
        if isinstance(instruction, (jvm.InvokeStatic, jvm.Return)):
            return False
        if isinstance(instruction, jvm.Load) and instruction.index in changed_local_indices:
            return False
    return True


def execute_input(
    bc: jpamb.Bytecode,
    methodid: jvm.AbsMethodID,
    inp: jpamb.case.Input,
    max_steps: int = 2000,
) -> tuple[set, str | None, list[tuple[str, int, int]]]:
    """Runs a single input through the dynamic interpreter, tracking coverage, behavior, and dynamic reads."""
    state = initial(bc, methodid, inp)
    recorded_reads: list[tuple[str, int, int]] = []
    state.recorded_reads = recorded_reads
    seen_states = set()
    snapshots = ExecutionSnapshots()
    run_pcs = set()
    executed_path: list[jvmc.PC] = []
    loop_visits: dict[tuple, tuple[int, tuple]] = {}

    for _ in range(max_steps):
        pc, state = step(bc, state)
        run_pcs.add(pc)
        if isinstance(state, str):
            return run_pcs, state, recorded_reads

        snapshot = snapshots.snapshot(state)
        if snapshot in seen_states:
            return run_pcs, "*", recorded_reads
        seen_states.add(snapshot)
        executed_path.append(pc)

        callers, (next_pc, operand_stack, current_locals), heap = snapshot
        if next_pc.method != pc.method or next_pc.offset > pc.offset:
            continue

        loop_key = (next_pc, callers, operand_stack, heap)
        previous_visit = loop_visits.get(loop_key)
        loop_visits[loop_key] = (len(executed_path), current_locals)
        if previous_visit is None:
            continue

        loop_start, previous_locals = previous_visit
        loop_path = executed_path[loop_start:]
        if loop_is_independent_of_changed_locals(bc, loop_path, previous_locals, current_locals):
            return run_pcs, "*", recorded_reads

    return run_pcs, None, recorded_reads


def run_initial_seeds(
    bc: jpamb.Bytecode,
    methodid: jvm.AbsMethodID,
    suite: jpamb.Suite,
    structure: list,
    max_steps: int = 2000,
    *,
    smith_results: dict[str, list[AbstractSmith]] | None = None,
    integer_operations: tuple[IntegerOperation, ...] = (),
) -> tuple[set[str], set, list[jpamb.case.Input], set[jpamb.case.Input], list]:
    """runs analysis using given inputs."""
    behaviors: set[str] = set()
    pc_coverage: set = set()
    used_corpus: set[jpamb.case.Input] = set()

    corpus = []
    if smith_results is None:
        smith_results = smith_outcomes(bc, methodid)
    for raw_seed in analysis_inputs(
        methodid, suite, smith_results=smith_results, integer_operations=integer_operations
    ):
        norm_values = tuple(
            jpamb.case.Array(v.contains, tuple(v.values))
            if isinstance(v, jpamb.case.Array) and not isinstance(v.values, tuple)
            else v
            for v in raw_seed.values
        )
        raw_seed = jpamb.case.Input(norm_values)
        corpus.append(raw_seed)

    if not corpus:
        corpus = [jpamb.case.Input(())]

    for seed in list(corpus):
        used_corpus.add(seed)
        run_pcs, behavior, recorded = execute_input(bc, methodid, seed, max_steps)
        pc_coverage.update(run_pcs)
        if behavior:
            behaviors.add(behavior)
        for field in recorded:
            if field not in structure:
                structure.append(field)

    structure.sort(key=lambda f: (f[1], f[2]))
    return behaviors, pc_coverage, corpus, used_corpus, structure


def fuzz_coverage(
    bc: jpamb.Bytecode,
    methodid: jvm.AbsMethodID,
    corpus: list[jpamb.case.Input],
    used_corpus: set[jpamb.case.Input],
    pc_coverage: set,
    structure: list,
    dictionary,
    budget: int = 200,
    max_steps: int = 2000,
    *,
    smith_results: dict[str, list[AbstractSmith]] | None = None,
    known_behaviors: set[str] | None = None,
    integer_operations: tuple[IntegerOperation, ...] = (),
) -> set[str]:
    """Mutate corpus inputs, using static Smith states to target unseen outcomes."""
    behaviors: set[str] = set()
    seen_in_seeds = known_behaviors or set()
    pending_targets: dict[str, list[AbstractSmith]] = {}
    for outcome, states in (smith_results or {}).items():
        if outcome in seen_in_seeds:
            continue
        eligible = [
            smith for smith in states
            if not smith.is_bot and (smith.length.min or 0) <= MAX_SMITH_SEED_LENGTH
        ]
        if eligible:
            pending_targets[outcome] = eligible

    for attempts_left in range(budget, 0, -1):
        if not corpus:
            break
        seed = random.choice(corpus)
        target = None
        # Alternate guided and ordinary mutations. Give each unseen outcome
        # equal weight, even if it has more Smith states than another outcome.
        if pending_targets and attempts_left % 2 == 0:
            outcome = random.choice(list(pending_targets))
            target = random.choice(pending_targets[outcome])
        mutant = mutate_input(
            seed, structure, dictionary, target=target, integer_operations=integer_operations
        )
        if target is not None and mutant in used_corpus:
            mutant = mutate_input(seed, structure, dictionary, integer_operations=integer_operations)
        if mutant in used_corpus:
            continue
        used_corpus.add(mutant)

        run_pcs, behavior, recorded = execute_input(bc, methodid, mutant, max_steps)
        if behavior:
            behaviors.add(behavior)
            # Retire the outcome that actually occurred, even on an ordinary mutation.
            pending_targets.pop(behavior, None)

        if run_pcs - pc_coverage:
            pc_coverage.update(run_pcs)
            corpus.append(mutant)
            for field in recorded:
                if field not in structure:
                    structure.append(field)
            structure.sort(key=lambda f: (f[1], f[2]))

    return behaviors


def analyse():
    """The dynamic analysis: initial seeds + coverage-based fuzzing."""
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
    BUDGET = 200

    dictionary = get_method_dictionary(methodid, suite)
    structure = list(get_bitstring_structure(methodid, suite))
    smith_results = smith_outcomes(bc, methodid)
    integer_operations = get_integer_operations(methodid, suite)

    #run on initial inputs from dictionary
    behaviors, pc_coverage, corpus, used_corpus, structure = run_initial_seeds(
        bc, methodid, suite, structure, max_steps=MAX_STEPS, smith_results=smith_results,
        integer_operations=integer_operations,
    )

    #coverage based fuzzing.
    fuzz_behaviors = fuzz_coverage(
        bc,
        methodid,
        corpus,
        used_corpus,
        pc_coverage,
        structure,
        dictionary,
        budget=BUDGET,
        max_steps=MAX_STEPS,
        smith_results=smith_results,
        known_behaviors=behaviors,
        integer_operations=integer_operations,
    )
    behaviors.update(fuzz_behaviors)

    for query in jpamb.QUERIES:
        if query in behaviors:
            if query == "*":
                print(f"{query};timeout")
            else:
                print(f"{query};found")
        else:
            print(f"{query};not-found")

