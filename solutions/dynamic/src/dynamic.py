import random
import sys

import jpamb
import jvm
import jvm.state as jvmc

#our group has added these imports:
import string

def binary(op, v1: int, v2: int) -> int | str:
    match op:
        case jvm.BinaryOpr.Div:
            try:
                return v1 // v2
            except ZeroDivisionError:
                return "divide by zero"
        
        case jvm.BinaryOpr.Add:
            return v1 + v2
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


def step(bc: jpamb.Bytecode, state: jvmc.State) -> tuple[jvmc.PC, jvmc.State | str]:
    assert isinstance(state, jvmc.State), f"expected state but got {state}"
    frame = state.frames.peek()
    pc = frame.pc
    opr = bc[pc]
    output = state
    print(f"Stepping {pc}:\n > {opr}", file=sys.stderr)
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

        case jvm.Return(type=jvm.Int()):
            v1 = frame.stack.pop()
            state.frames.pop()
            if state.frames:
                frame = state.frames.peek()
                frame.stack.push(v1)
                frame.pc += 1
            else:
                output = "ok"
                
        case jvm.Return(type=none):
            state.frames.pop()
            if state.frames:
                frame = state.frames.peek()
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
            try:
                ref = state.heap.new(jvmc.HeapArray(jvm.Int(), [0] * count.value))
                frame.stack.push(ref)
                frame.pc += 1
            except MemoryError:
                raise Exception("failed to create array, array too large for memory")

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
    # 1. come up with possible inputs
    for p in methodid.extension.params:
        match p:
            case jvm.Int():
                input.append(jpamb.case.Int(rand.randint(-(1 << 31), 1 << 31)))
                #input.append(jpamb.case.Int(696969))
            case jvm.Boolean():
                input.append(jpamb.case.Boolean(1 == rand.randint(0, 1)))
            case jvm.Array(contains=jvm.Int()):
                rand_upperbound = rand.randint(1, 10000)
                rand_length = rand.randint(0,rand_upperbound)
                array = []
                for i in range(rand_length):
                    rand_val = rand.randint(-(1 << 31), 1 << 31)
                    array.append(rand_val)
                input.append(jpamb.case.Array(jvm.Int(),array))
            case jvm.Array(contains=jvm.Char()):
                rand_upperbound = rand.randint(1, 10000)
                rand_length = rand.randint(0,rand_upperbound)
                array = []
                for i in range(rand_length):
                    random_int = rand.randint(32, 126)
                    rand_char = chr(random_int)
                    array.append(rand_char)
                input.append(jpamb.case.Array(jvm.Char(),array))
            case jvm.Object(jvm.ClassName("java.lang.String")):
                rand_length = rand.randint(0, 10000)
                random_string = ''.join(random.choices(string.ascii_letters + string.digits, k=rand_length))
                input.append(jpamb.case.String(random_string))

            case a:
                raise NotImplementedError(
                    f"Don't know how to create random values for {a}"
                )

    return jpamb.case.Input(input)




    



def analyse():
    """The dynamic analysis, e.g. in this case a (dumb) fuzzer."""

    methodid = jpamb.getmethodid(
        "dynamic",
        "1.0",
        "Bit Diddlers",
        ["dynamic", "python"],
        for_science=True,
    )

    suite, eff = jpamb.setup()
    bc = jpamb.Bytecode(suite, eff, {})

    MAX_STEPS = 200

    import random

    # Make the randomness deterministic
    rand = random.Random(0)

    behaviors = set()
    # Try 10 random inputs
    for i in range(10):
        input = fuzz_input(rand, methodid)
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
