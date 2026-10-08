import sys
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

from abstractions import SignSet

import jpamb
import sexpr
from jpamb import jvm
from jvm.state import PC, StackInt


@dataclass(frozen=True)
class State(sexpr.AsSExpr):
    locals: tuple[SignSet, ...]
    stack: tuple[SignSet, ...]

    def __post_init__(self):
        assert isinstance(self.locals, tuple)
        assert isinstance(self.stack, tuple)

    def __str__(self):
        return f"{', '.join(map(str, self.locals))}/{':'.join(map(str, self.stack))}"

    def __or__(self, other):
        assert isinstance(other, State), f"Expected State but got {other!r}"
        assert len(self.stack) == len(other.stack), "Stacks should be equal lenght"
        assert len(self.locals) == len(other.locals), "Locals should be equal lenght"

        return State(
            tuple(s1 | s2 for s1, s2 in zip(self.locals, other.locals)),
            tuple(s1 | s2 for s1, s2 in zip(self.stack, other.stack)),
        )

    def push(self, value: SignSet):
        assert isinstance(value, SignSet), f"Expected sign set but got {value}"
        return State(self.locals, self.stack + (value,))

    def pop(self, number=1):
        return self.stack[-number:], State(self.locals, self.stack[:-number])

    def load(self, index):
        return self.locals[index]

    def store(self, index, value):
        return State(
            tuple(self.locals[:index]) + (value,) + tuple(self.locals[index + 1 :]),
            self.stack,
        )


def manystep(
    bc: jpamb.Bytecode,
    pc: PC,
    state: State,
) -> Iterable[tuple[PC, object] | str]:
    opr = bc[pc]
    match opr:
        case jvm.Get(static=True, field=field):
            # Hack - Only handle the assertion case
            assert field.extension.name == "$assertionsDisabled"

            # Hack - Assuming assertions are never disabled
            va = SignSet.abstract([StackInt(0)])

            yield (pc + 1, state.push(va))

        case jvm.Ifz(condition=op, target=target):
            [val], after = state.pop(1)

            for res in SignSet.compare(val, SignSet.abstract([StackInt(0)]), op):
                match res:
                    case True:
                        yield (pc % target, after)
                    case False:
                        yield (pc + 1, after)
                    case err:
                        yield err
        case jvm.NewArray(type=t, dim=dim):
            popped_val,popped_state = state.pop() # size of array, ignored
            abstract_array = SignSet.abstract(StackInt(1))
            yield (pc+1,popped_state.push(abstract_array)) # currently just pushes to the stack as no heap exists
        case jvm.ArrayLength():
            (ref,), popped_state = state.pop(1)
            if StackInt(0) in ref:
                yield "null pointer"
            if (StackInt(1) in ref) or (StackInt(-1) in ref):
                length = SignSet(frozenset({0,1})) # length thrown away upon creation
                yield (pc+1, popped_state.push(length))
        case jvm.ArrayLoad(type=t):
            (ref, index),popped_state = state.pop(2)
            
            if StackInt(0) in ref:
                yield "null pointer"
            yield "out of bounds"
            if (StackInt(1) in ref) or (StackInt(-1) in ref):
                new_state = popped_state.push(SignSet.top()) # we assume signs could be anything
                yield (pc + 1, new_state)
        case jvm.ArrayStore(type=t):
            (ref, index, value),new_state = state.pop(3)
            if StackInt(0) in ref:
                yield "null pointer"
            yield "out of bounds"
            if (StackInt(1) in ref) or (StackInt(-1) in ref):
                yield (pc+1,new_state)
        case jvm.Incr(index=ind, amount = amo):
            assert isinstance(amo,int)
            abst = SignSet.abstract(StackInt(amo))
            stored_set = state.load(ind)
            new_val,errors = SignSet.arithmetic(abst,stored_set,jvm.BinaryOpr.Add)
            for error in errors:
                yield error
            
            new_state  =state.store(ind,new_val)
            yield (pc+1,new_state)


        case jvm.Dup():
            values,popped_state = state.pop()
            new_state = popped_state.push(values[0])
            yield(pc+1,new_state.push(values[0]))
        case jvm.ArrayStore(type=jvm.Int()):
            popped, new_state = state.pop(3)
            yield (pc + 1, new_state)
        case jvm.Store(type=type,index = index):
            popped_value, popped_state = state.pop(1)
            actual_value = popped_value[0]
            new_state = popped_state.store(index, actual_value)
            yield (pc+1,new_state)
        #case jvm.IAStore():
        #    popped, new_state = state.pop(3)
    #
        #    arrayref_signs = popped[0]
        #    index_signs = popped[1]     
        #    value_signs = popped[2]  
        #    updated_array_signs = arrayref_signs | value_signs # union of sign sets
        #    
        #    # since no heap we dont push
        #    yield (pc + 1, new_state)
        #case jvm.IALoad():
        #    popped, popped_state = state.pop(2)
        #    arrayref_signs = popped[0]
        #    index_signs = popped[1] # Ignored
        #    # We push the array's signs back onto the stack as the "loaded value"
        #    new_state = popped_state.push(arrayref_signs)
        #    
        #    yield (pc + 1, new_state) 
        case jvm.Load(index=i):
            va = state.load(i)
            yield (pc + 1, state.push(va))
        case jvm.Push(type=t,value=i):
            assert isinstance(t,jvm.StackType)
            yield (pc+1,state.push(SignSet.abstract([StackInt(i)])))

        case jvm.Goto(target=t):
            yield (pc % t, state)
        case jvm.If(condition=op,target=target):
            [val1,val2],after = state.pop(2)
            for res in SignSet.compare(val1,val2,op):
                match res:
                    case True:
                        yield (pc % target, after)
                    case False:
                        yield (pc + 1, after)
                    case err:
                        yield err
        case jvm.Binary(operant=op):
            [v1, v2], after = state.pop(2)
            res, errors = SignSet.arithmetic(v1, v2, op)
            for err in errors:
                yield err
            if res.signs:
                yield (pc + 1, after.push(res))
        case jvm.Return(type=None):
            yield "ok"
        case jvm.Return(type=t):
            # Hack -- we assume that we always return.
            yield "ok"
        case jvm.New(classname=jvm.ClassName("java.lang.AssertionError")):
            # Hack -- if we create an assertion error, we probably also throw it.
            yield "assertion error"

        
        # this case was added by us for debuggning purposes
        case _:
            raise NotImplementedError(f"Unimplemented opcode at {pc}: {opr} ({opr!r})")


def initialstate(
    bc: jpamb.Bytecode,
    methodid: jvm.AbsMethodID,
    inputs: jpamb.Input | None,
) -> dict[PC, State]:
    method = bc.getmethod(methodid)
    locals = [SignSet.bot()] * method.max_locals

    if inputs is None:
        for i, p in enumerate(methodid.extension.params):
            locals[i] = SignSet.top()
    else:
        for i, x in enumerate(inputs.values):
            match x:
                case jpamb.case.Boolean(value=value):
                    locals[i] = SignSet.abstract([StackInt(int(value))])
                case jpamb.case.Int(value=value):
                    locals[i] = SignSet.abstract([StackInt(int(value))])
                case jpamb.case.Array():
                    locals[i] = SignSet.from_sign("+")
                case _:
                    raise NotImplementedError(f"Unsupported value {x!r}")

    state = State(tuple(locals), ())
    return {PC(methodid, 0): state}


@dataclass
class AbstractInterpreter:
    bc: jpamb.Bytecode
    worklist: deque[PC]
    states: dict[PC, State]

    @staticmethod
    def initial(bc: jpamb.Bytecode, methodid: jvm.AbsMethodID, inputs):
        states = initialstate(bc, methodid, inputs)
        worklist = deque(states.keys())

        return AbstractInterpreter(bc, worklist, states)

    def step(self) -> tuple[PC, set[str]]:
        pc = self.worklist.popleft() # pop for DFS, popleft for BFS

        print(f"Stepping {pc}:\n > {self.bc[pc]}", file=sys.stderr)

        finals = set()

        for res in manystep(self.bc, pc, self.states[pc]):
            if isinstance(res, str):
                finals.add(res)
            else:
                pc_, st = res

                before = self.states.get(pc_, None)
                if before is None:
                    after = st
                else:
                    after = before | st
                if before is None or after != before:
                    self.states[pc_] = after
                    self.worklist.append(pc_)

        return pc, finals


def interpret():
    """The static analysis"""
    methodid, input, steps = jpamb.getcase(
        "static",
        "1.0",
        "Bit Diddlers",
        ["static", "python"],
        for_science=True,
    )
    suite, eff = jpamb.setup()
    bc = jpamb.Bytecode(suite, eff, {})

    ai = AbstractInterpreter.initial(bc, methodid, input)

    x = jpamb.emit_init(ai.states)

    while steps > 0 and ai.worklist:
        pc, final = ai.step()
        for f in final:
            jpamb.emit_step(x, pc, f, depth=1)
            steps -= 1

        x = jpamb.emit_step(x, pc, ai.states, depth=1)
        steps -= 1


def analyse():
    """The static analysis"""

    methodid = jpamb.getmethodid(
        "static",
        "1.0",
        "Bit Diddlers",
        ["static", "python"],
        for_science=True,
    )

    suite, eff = jpamb.setup()
    bc = jpamb.Bytecode(suite, eff, {})

    steps = 300

    ai = AbstractInterpreter.initial(bc, methodid, None)

    final = set()
    while steps > 0 and ai.worklist:
        _pc, finals = ai.step()
        final |= finals
        steps -= 1

    for f in jpamb.QUERIES:
        if f not in final:
            print(f"{f};no")
        else:
            print(f"{f};maybe")
