import heapq
import sys
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from dataclasses import astuple
from abstractions import Interval, AbstractSmith, Drawn
from java_literals import convert_literals, get_literals_in_method

import jpamb
import sexpr
from jpamb import jvm
from jvm.state import PC, StackInt


@dataclass(frozen=True)
class State(sexpr.AsSExpr):
    locals: tuple[int, ...] # list of id's
    stack: tuple[int, ...] # list of id's
    store: tuple[tuple[int, Interval], ...] # mapping id's to intervals
    next_id: int = 0
    smith: AbstractSmith = AbstractSmith.bot() # start with no smith
    def __post_init__(self):
        assert isinstance(self.locals, tuple)
        assert isinstance(self.stack, tuple)

    def __str__(self):
        return f"{', '.join(map(str, self.locals))}/{':'.join(map(str, self.stack))}"

    def __eq__(self, other: "State") -> bool:
        """Checks if the actual intervals are identical, ignoring raw ID numbers."""
        if len(self.locals) != len(other.locals) or len(self.stack) != len(other.stack):
            return False
        if self.smith != other.smith:
            return False
        for id1, id2 in zip(self.locals + self.stack, other.locals + other.stack):
            left, right = self.get_val(id1), other.get_val(id2)
            if left != right:
                return False
            left_sources = left.bit_sources() if isinstance(left, Drawn) else None
            right_sources = right.bit_sources() if isinstance(right, Drawn) else None
            if left_sources != right_sources:
                return False
        return True
    
    def __or__(self, other):
        assert isinstance(other, State), f"Expected State but got {other!r}"
        assert len(self.stack) == len(other.stack), "Stacks should be equal lenght"
        assert len(self.locals) == len(other.locals), "Locals should be equal lenght"

        new_locals, new_stack, new_store = [], [], []
        next_id = max(self.next_id, other.next_id)

       
        merged_map = {}
        def merge_ids(id1, id2):
            nonlocal next_id
            pair = (id1, id2)
            if pair in merged_map:
                return merged_map[pair]
            joined_val = self.get_val(id1) | other.get_val(id2)
            new_id = next_id
            next_id += 1
            new_store.append((new_id, joined_val))
            merged_map[pair] = new_id
            return new_id

        for id1, id2 in zip(self.locals, other.locals):
            new_locals.append(merge_ids(id1, id2))

        for id1, id2 in zip(self.stack, other.stack):
            new_stack.append(merge_ids(id1, id2))
        return State(tuple(new_locals), tuple(new_stack), tuple(new_store), next_id).gc()

    def __or__(self, other: "State"):
        assert isinstance(other, State), f"Expected State but got {other!r}"
        assert len(self.stack) == len(other.stack), "Stacks should be equal lenght"
        assert len(self.locals) == len(other.locals), "Locals should be equal lenght"
        
        new_locals, new_stack, new_store = [], [], []
        next_id = max(self.next_id, other.next_id)

        for id1, id2 in zip(self.locals, other.locals):
            joined_val = self.get_val(id1) | other.get_val(id2)
            new_locals.append(next_id)
            new_store.append((next_id, joined_val))
            next_id += 1

        for id1, id2 in zip(self.stack, other.stack):
            joined_val = self.get_val(id1) | other.get_val(id2)
            new_stack.append(next_id)
            new_store.append((next_id, joined_val))
            next_id += 1
        smith = self.smith | other.smith
        return State(tuple(new_locals), tuple(new_stack), tuple(new_store), next_id, smith).gc()

    def widen(self, other: "State", K: list[int] = None) -> "State":
        assert isinstance(other, State)
        new_locals, new_stack, new_store = [], [], []
        next_id = max(self.next_id, other.next_id)
        merged_map = {}

        def merge_ids(id1, id2):
            nonlocal next_id
            pair = (id1, id2)
            if pair in merged_map:
                return merged_map[pair] # Reuse ID to preserve symbol map links
            joined_val = self.get_val(id1) | other.get_val(id2)
            new_id = next_id
            next_id += 1
            new_store.append((new_id, joined_val))
            merged_map[pair] = new_id
            return new_id
        
        for id1, id2 in zip(self.locals, other.locals):
            joined_val = self.get_val(id1).widen(other.get_val(id2), K)
            new_locals.append(next_id)
            new_store.append((next_id, joined_val))
            next_id += 1

        for id1, id2 in zip(self.stack, other.stack):
            joined_val = self.get_val(id1).widen(other.get_val(id2), K)
            new_stack.append(next_id)
            new_store.append((next_id, joined_val))
            next_id += 1
        
        smith = self.smith.widen(other.smith, K)
        return State(tuple(new_locals), tuple(new_stack), tuple(new_store), next_id, smith).gc()

    def get_val(self, sym_id: int) -> Interval:
        for s, val in self.store:
            if s == sym_id: return val
        return Interval.top()
    def update_val(self, sym_id: int, val: Interval) -> "State":
        new_store = tuple((s, (val if s == sym_id else v)) for s, v in self.store)
        return replace(self, store=new_store)
    def create_val(self, val: Interval) -> tuple[int, "State"]:
        sym_id = self.next_id
        new_store = self.store + ((sym_id, val),)
        return sym_id, replace(self, store=new_store, next_id=self.next_id + 1)
    
    def push_id(self, sym_id: int):
        return replace(self, stack=self.stack + (sym_id,))
    def pop_ids(self, number=1) -> tuple[tuple[int, ...], "State"]:
        return self.stack[-number:], replace(self, stack=self.stack[:-number])
    def read_local(self, index: int) -> int:
        return self.locals[index]

    def write_local(self, index: int, sym_id: int):
        new_locals = tuple(self.locals[:index]) + (sym_id,) + tuple(self.locals[index + 1 :])
        return replace(self, locals=new_locals)

    def gc(self) -> "State":
        active_ids = set(self.locals) | set(self.stack)
        new_store = tuple((s, v) for s, v in self.store if s in active_ids)
        return replace(self, store=new_store)

SMITH_TYPE = jvm.Object(jvm.ClassName("jpamb.utils.Smith"))


def refine(state: State, sym_id: int, new_val: Interval) -> State | None:
    """Narrow a value on a branch. If the value was read from the Smith,
    the Smith learns the bits it was read from."""
    old = state.get_val(sym_id)
    if isinstance(old, Drawn):
        new_val = Drawn(new_val.min, new_val.max, old.start, old.width, old.sources)
        smith = state.smith.learn_sources(old.bit_sources(), new_val)
        if smith.is_bot:
            return None
        state = replace(state, smith=smith)
    return state.update_val(sym_id, new_val)


def straight_line_return(bc: jpamb.Bytecode, method: jvm.AbsMethodID, state: State) -> Interval:
    """Summarize a helper that computes a return value without branching or calls."""
    for offset, opcode in enumerate(bc.getmethod(method).opcodes):
        if isinstance(opcode, jvm.Return) and opcode.type is not None:
            return state.get_val(state.stack[-1])
        if not isinstance(opcode, (jvm.Load, jvm.Push, jvm.Store, jvm.Bitopr)):
            break
        transition = next(iter(manystep(bc, PC(method, offset), state)), None)
        if transition is None:
            break
        _, state = transition
    return Interval.top()


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
            sym_id, after = state.create_val(Interval.abstract([StackInt(0)]))
            yield (pc + 1, after.push_id(sym_id))

        case jvm.Ifz(condition=op, target=target):
            [sym_id], after = state.pop_ids(1)
            val = after.get_val(sym_id)
            true_val = narrow_ifz(val, op, True) 
            false_val = narrow_ifz(val, op, False)

            if not true_val.is_bot: #yield true branch if not bottom
                out_t = refine(after, sym_id, true_val)
                if out_t is not None:
                    yield (pc % target, out_t)
                
            if not false_val.is_bot: # yield false branch if not bottom
                out_f = refine(after, sym_id, false_val)
                if out_f is not None:
                    yield (pc + 1, out_f)
        case jvm.NewArray(type=t, dim=dim):
            [size_id], after = state.pop_ids(1)
            size = after.get_val(size_id)
            ref = size + Interval(min=1, max=1)
            sym_id, after = after.create_val(ref)
            yield (pc + 1, after.push_id(sym_id))
        case jvm.ArrayLength():
            [ref_id], after = state.pop_ids(1)
            ref = after.get_val(ref_id)
            if StackInt(0) in ref: yield "null pointer"
            if not (ref.min == 0 and ref.max == 0): 
                length = ref - Interval(min=1, max=1)
                sym_id, after = after.create_val(length)
                yield (pc + 1, after.push_id(sym_id))
        case jvm.ArrayLoad(type=t):
            [ref_id, idx_id], after = state.pop_ids(2)
            ref = after.get_val(ref_id)
            idx = after.get_val(idx_id)
            
            if StackInt(0) in ref: yield "null pointer"
            
            if not (ref.min == 0 and ref.max == 0): 
                length = ref - Interval(min=1, max=1)
                is_neg = True in idx.compare(Interval(min=0, max=0), jvm.CmpOpr.Lt)
                is_too_big = True in idx.compare(length, jvm.CmpOpr.Ge)
                if is_neg or is_too_big: yield "out of bounds"
                
                is_valid_pos = True in idx.compare(Interval(min=0, max=0), jvm.CmpOpr.Ge)
                is_valid_len = True in idx.compare(length, jvm.CmpOpr.Lt)
                if is_valid_pos and is_valid_len:
                    sym_id, after = after.create_val(Interval.top())
                    yield (pc + 1, after.push_id(sym_id))
        case jvm.ArrayStore(type=t):
            [ref_id, idx_id, val_id], after = state.pop_ids(3)
            ref = after.get_val(ref_id)
            idx = after.get_val(idx_id)
            

            if StackInt(0) in ref: yield "null pointer"
            if not (ref.min == 0 and ref.max == 0): 
                length = ref - Interval(min=1, max=1)
                is_neg = True in idx.compare(Interval(min=0, max=0), jvm.CmpOpr.Lt)
                is_too_big = True in idx.compare(length, jvm.CmpOpr.Ge)
                if is_neg or is_too_big: yield "out of bounds"
                    
                is_valid_pos = True in idx.compare(Interval(min=0, max=0), jvm.CmpOpr.Ge)
                is_valid_len = True in idx.compare(length, jvm.CmpOpr.Lt)
                if is_valid_pos and is_valid_len:
                    yield (pc + 1, after)
        case jvm.Incr(index=ind, amount = amo):
            assert isinstance(amo, int)
            stored_id = state.read_local(ind)
            stored_val = state.get_val(stored_id)
            abst = Interval.abstract([StackInt(amo)])
            
            new_val, errors = Interval.arithmetic(abst, stored_val, jvm.BinaryOpr.Add)
            for error in errors: yield error
            
            sym_id, after = state.create_val(new_val)
            yield (pc + 1, after.write_local(ind, sym_id))


        case jvm.Dup():
            [sym_id], after = state.pop_ids(1)
            yield (pc + 1, after.push_id(sym_id).push_id(sym_id))
        
        case jvm.Store(type=type,index = index):
            [sym_id], after = state.pop_ids(1)
            yield (pc + 1, after.write_local(index, sym_id))
        case jvm.InvokeStatic(method=method_id):
            num_args = len(method_id.extension.params)
            args_ids, after = state.pop_ids(num_args) if num_args else ((), state)  
            target_method = bc.getmethod(method_id)
            callee_locals = list(args_ids) + [0] * (target_method.max_locals - len(args_ids))
            callee_state = State(tuple(callee_locals), (), after.store, after.next_id, after.smith)
            for i in range(len(args_ids), target_method.max_locals):
                sym_id, callee_state = callee_state.create_val(Interval.bot())
                callee_locals[i] = sym_id
            callee_state = replace(callee_state, locals=tuple(callee_locals))
            yield (PC(method_id, 0), callee_state)
            if SMITH_TYPE in method_id.extension.params and not after.smith.is_bot:
                # The callee may have read bits, so after the call the cursor can be anywhere from here on.
                # NOTE: forgets how many bits the callee read; return the callee's smith if that matters.
                smith = replace(after.smith, cursor=after.smith.cursor + Interval(0, None))
                after = replace(after, smith=smith) 
            ret_type = method_id.extension.return_type
            match ret_type:
                case None: next_state = after
                case jvm.Array():
                    sym_id, next_state = after.create_val(Interval(min=0, max=None))
                    next_state = next_state.push_id(sym_id)
                case jvm.Int() | jvm.Boolean() if any(
                    isinstance(after.get_val(arg), Drawn) for arg in args_ids
                ):
                    sym_id, next_state = after.create_val(straight_line_return(bc, method_id, callee_state))
                    next_state = next_state.push_id(sym_id)
                case _:
                    sym_id, next_state = after.create_val(Interval.top())
                    next_state = next_state.push_id(sym_id)
            yield (pc + 1, next_state)
        case jvm.Load(index=i):
            sym_id = state.read_local(i)
            yield (pc + 1, state.push_id(sym_id))
        case jvm.Push(value=str()):
            #string are abstracted as non null references
            sym_id, after = state.create_val(Interval(min=1, max=None))
            yield (pc + 1, after.push_id(sym_id))
        case jvm.InvokeVirtual(method=m) if m.extension.name == "equals":
            [recv_id, _], after = state.pop_ids(2)
            recv = after.get_val(recv_id)
            if StackInt(0) in recv: yield "null pointer"
            if not (recv.min == 0 and recv.max == 0):
                sym_id, after = after.create_val(Interval(min=0, max=None))
                yield (pc + 1, after.push_id(sym_id))
        case jvm.InvokeVirtual(method=m) if (
            m.extension.name == "charAt"
            and len(m.extension.params) == 1
            and isinstance(m.extension.params[0], jvm.Int)
            and m.extension.return_type == jvm.Char()
        ):
            [recv_id, idx_id], after = state.pop_ids(2)
            recv = after.get_val(recv_id)
            idx = after.get_val(idx_id)
            if StackInt(0) in recv: yield "null pointer"
            if not idx.is_bot and not (recv.min == 0 and recv.max == 0):
                # The reference abstraction does not track string length.
                yield "out of bounds"
                if idx.max is None or idx.max >= 0:
                    sym_id, after = after.create_val(Interval(min=0, max=65535))
                    yield (pc + 1, after.push_id(sym_id))
        case jvm.InvokeInterface(method=m) if m.extension.name == "draw":
            # draw() reads 1 bit. draw(n) reads n bits; n is on top of the stack.
            if m.extension.params:
                [_, n_id], after = state.pop_ids(2)
                count = after.get_val(n_id)
            else:
                [_], after = state.pop_ids(1)
                count = Interval(1, 1)

            if count.is_bot:
                return
            if count.min is None or count.min < 0:
                yield "illegal argument"
            if count.max is not None and count.max < 0:
                return
            nonnegative = Interval(max(0, count.min or 0), count.max)
            if (result := after.smith.draw_counts(nonnegative)) is not None:
                value, smith = result
                sym_id, out = replace(after, smith=smith).create_val(value)
                yield (pc + 1, out.push_id(sym_id))
        case jvm.Push(type=t,value=i):
            assert isinstance(t, jvm.StackType)
            sym_id, after = state.create_val(Interval.abstract([StackInt(i)]))
            yield (pc + 1, after.push_id(sym_id))
        case jvm.Goto(target=t):
            yield (pc % t, state)
        case jvm.If(condition=op,target=target):
            [id1, id2], after = state.pop_ids(2)
            v1, v2 = after.get_val(id1), after.get_val(id2)
            t_v1, t_v2 = refine_if_bounds(v1, v2, op, is_true=True)
            f_v1, f_v2 = refine_if_bounds(v1, v2, op, is_true=False)

            for target_pc, left, right in ((pc % target, t_v1, t_v2), (pc + 1, f_v1, f_v2)):
                if left.is_bot or right.is_bot:
                    continue
                refined = refine(after, id1, left)
                if refined is not None:
                    refined = refine(refined, id2, right)
                if refined is not None:
                    yield (target_pc, refined)
        case jvm.Binary(operant=op):
            [id1, id2], after = state.pop_ids(2)
            v1, v2 = after.get_val(id1), after.get_val(id2)
            
            res, errors = Interval.arithmetic(v1, v2, op)
            for err in errors: yield err
            
            if not res.is_bot:
                sym_id, after = after.create_val(res)
                yield (pc + 1, after.push_id(sym_id))
        case jvm.Bitopr(type=jvm.Int(), operant=op):
            [id1, id2], after = state.pop_ids(2)
            v1, v2 = after.get_val(id1), after.get_val(id2)

            if op is jvm.BitOpr.And and isinstance(v2, Drawn) and v1.min == v1.max:
                v1, v2 = v2, v1
            res = v1.bitwise(v2, op)
            if not res.is_bot:
                sym_id, after = after.create_val(res)
                yield (pc + 1, after.push_id(sym_id))
        case jvm.Return(type=None):
            yield "ok"
        case jvm.Return(type=t):
            # Hack -- we assume that we always return.
            yield "ok"
        case jvm.New(classname=jvm.ClassName("java.lang.AssertionError")):
            # Hack -- if we create an assertion error, we probably also throw it.
            yield "assertion error"
        case jvm.Negate(type = jvm.Int()):
            [vid], after = state.pop_ids(1)
            v = after.get_val(vid)
            zero_set = Interval.abstract([StackInt(0)])
            negv, errors = zero_set.arithmetic(v, jvm.BinaryOpr.Sub)
            for error in errors: yield error
            sym_id, after = after.create_val(negv)
            yield (pc + 1, after.push_id(sym_id))
        case jvm.Cast(from_=jvm.Int(), to_=jvm.Short()):
            [vid], after = state.pop_ids(1)
            val = after.get_val(vid)
            res = val if val == Interval(min=0, max=0) else Interval.top()
            sym_id, after = after.create_val(res)
            yield (pc + 1, after.push_id(sym_id))
        # this case was added by us for debuggning purposes
        case _:
            raise NotImplementedError(f"Unimplemented opcode at {pc}: {opr} ({opr!r})")


def initialstate(
    bc: jpamb.Bytecode,
    methodid: jvm.AbsMethodID,
    inputs: jpamb.Input | None,
) -> dict[PC, State]:
    method = bc.getmethod(methodid)
    state = State(tuple([0] * method.max_locals), (), (), 0)
    locals = [0] * method.max_locals 
    smith = AbstractSmith.bot()  # stays bot if the method takes no Smith

    if inputs is None:
        for i, p in enumerate(methodid.extension.params):
            if p == SMITH_TYPE:
                smith = AbstractSmith.unknown()  # any bitstring
                sym_id, state = state.create_val(Interval(min=1, max=None))  # non-null reference
            else:
                sym_id, state = state.create_val(Interval.top())
            locals[i] = sym_id
       
    else:
        for i, x in enumerate(inputs.values):
            match x:
                case jpamb.case.Boolean(value=value)| jpamb.case.Int(value=value):
                    sym_id, state = state.create_val(Interval.abstract([StackInt(int(value))]))
                    locals[i] = sym_id
                case jpamb.case.Array() | jpamb.case.String():
                    sym_id, state = state.create_val(Interval(min=0,max=None))
                    locals[i] = sym_id
                case jpamb.case.Smith(value=value):
                    smith = AbstractSmith.from_bits(value)  # exactly this bitstring
                    sym_id, state = state.create_val(Interval(min=1, max=None))  # non-null reference
                    locals[i] = sym_id
                case _:
                    raise NotImplementedError(f"Unsupported value {x!r}")
    for i in range(len(locals)):
        if locals[i] == 0 and i >= (len(methodid.extension.params) if inputs is None else len(inputs.values)):
            sym_id, state = state.create_val(Interval.bot())
            locals[i] = sym_id
    state = State(tuple(locals), (), state.store, state.next_id, smith)
    return {PC(methodid, 0): state}


@dataclass
class AbstractInterpreter:
    bc: jpamb.Bytecode
    worklist: list[PC]
    states: dict[PC, State]
    k_set: list[int]
    # outcome -> {pc where it is raised: Smith state there}.
    # "*" (may run forever) is keyed by the target of a back edge.
    outcome_smiths: dict[str, dict[PC, AbstractSmith]] = field(default_factory=dict)
    forward_calls: dict[jvm.AbsMethodID, set[jvm.AbsMethodID]] = field(default_factory=dict)
    recursive_calls: set[tuple[jvm.AbsMethodID, jvm.AbsMethodID]] = field(default_factory=set)

    @staticmethod
    def initial(bc: jpamb.Bytecode, methodid: jvm.AbsMethodID, inputs):
        states = initialstate(bc, methodid, inputs)
        worklist = list(states.keys())
        raw = get_literals_in_method(methodid, bc.suite)
        converted = convert_literals(raw)
        k_set = set(converted.get(int, []))
        k_set.add(0)
        return AbstractInterpreter(bc, worklist, states, sorted(list(k_set)))

    def is_back_edge(self, source: PC, target: PC) -> bool:
        if source.method == target.method:
            return target.offset <= source.offset

        edge = (source.method, target.method)
        if edge in self.recursive_calls:
            return True
        callees = self.forward_calls.setdefault(source.method, set())
        if target.method in callees:
            return False

        # Keep the ordinary call graph acyclic. Widen on any new edge
        # that would close a cycle.
        pending = [target.method]
        visited = set()
        while pending:
            method = pending.pop()
            if method == source.method:
                self.recursive_calls.add(edge)
                return True
            if method not in visited:
                visited.add(method)
                pending.extend(self.forward_calls.get(method, ()))
        callees.add(target.method)
        return False

    def step(self, *, trace: bool = True) -> tuple[PC, set[str]]:
        self.worklist.sort(key=lambda p: p.offset, reverse=True)
        pc = self.worklist.pop() # pop for DFS, popleft for BFS

        if trace:
            print(f"Stepping {pc}:\n > {self.bc[pc]}", file=sys.stderr)

        finals = set()

        for res in manystep(self.bc, pc, self.states[pc]):
            if isinstance(res, str):
                finals.add(res)
                # states only grow, so the latest Smith at this pc covers the earlier ones
                self.outcome_smiths.setdefault(res, {})[pc] = self.states[pc].smith
            else:
                next_pc, next_state = res
                backward = self.is_back_edge(pc, next_pc)

                before = self.states.get(next_pc, None)
                if before is None:
                    after = next_state
                else:
                    joined = before | next_state
                    if backward:
                        after = before.widen(joined, self.k_set)
                    else:
                        after = joined
                    
                if before is None or after != before:
                    self.states[next_pc] = after
                    self.worklist.append(next_pc)
                if backward:
                    self.outcome_smiths.setdefault("*", {})[next_pc] = self.states[next_pc].smith

        return pc, finals

# helper function for invoke static
def analyze_method(
    bc: jpamb.Bytecode,
    method_id: jvm.AbsMethodID,
    args: tuple[Interval, ...],
    max_steps: int = 200,
) -> set[str]:
    method = bc.getmethod(method_id)
    locals_ = [Interval.bot()] * method.max_locals
    for i, arg in enumerate(args):
        locals_[i] = arg

    entry_pc = PC(method_id, 0)
    ai = AbstractInterpreter(
        bc,
        deque([entry_pc]),
        {entry_pc: State(tuple(locals_), ())},
    )

    outcomes = set()
    while ai.worklist and max_steps > 0:
        _, finals = ai.step()
        outcomes |= finals
        max_steps -= 1

    return outcomes

def narrow_ifz(val: Interval, op: jvm.CmpOpr, is_true: bool) -> Interval:
  
    if val.is_bot: return val
    if not is_true:
        inverses = {
            jvm.CmpOpr.Eq: jvm.CmpOpr.Ne, jvm.CmpOpr.Ne: jvm.CmpOpr.Eq,
            jvm.CmpOpr.Lt: jvm.CmpOpr.Ge, jvm.CmpOpr.Le: jvm.CmpOpr.Gt,
            jvm.CmpOpr.Gt: jvm.CmpOpr.Le, jvm.CmpOpr.Ge: jvm.CmpOpr.Lt
        }
        op = inverses.get(op, op)

    new_min, new_max = val.min, val.max
    match op:
        case jvm.CmpOpr.Eq:
            new_min = max(val.min, 0) if val.min is not None else 0
            new_max = min(val.max, 0) if val.max is not None else 0
        case jvm.CmpOpr.Ne:
            if val.min == 0 and val.max == 0: return Interval(1, 0)
            if val.min == 0: new_min = 1
            if val.max == 0: new_max = -1
        case jvm.CmpOpr.Lt:
            new_max = min(val.max, -1) if val.max is not None else -1
        case jvm.CmpOpr.Le:
            new_max = min(val.max, 0) if val.max is not None else 0
        case jvm.CmpOpr.Gt:
            new_min = max(val.min, 1) if val.min is not None else 1
        case jvm.CmpOpr.Ge:
            new_min = max(val.min, 0) if val.min is not None else 0

    res = Interval(new_min, new_max)
    return Interval(1, 0) if res.is_bot else res

def refine_if_bounds(v1: Interval, v2: Interval, op: jvm.CmpOpr, is_true: bool) -> tuple[Interval, Interval]:
    if not is_true:
        inverses = {
            jvm.CmpOpr.Eq: jvm.CmpOpr.Ne, jvm.CmpOpr.Ne: jvm.CmpOpr.Eq,
            jvm.CmpOpr.Lt: jvm.CmpOpr.Ge, jvm.CmpOpr.Le: jvm.CmpOpr.Gt,
            jvm.CmpOpr.Gt: jvm.CmpOpr.Le, jvm.CmpOpr.Ge: jvm.CmpOpr.Lt
        }
        op = inverses[op]

    new_v1_min, new_v1_max = v1.min, v1.max
    new_v2_min, new_v2_max = v2.min, v2.max

    match op:
        case jvm.CmpOpr.Lt:
            if v2.max is not None: new_v1_max = min(v1.max, v2.max - 1) if v1.max is not None else (v2.max - 1)
            if v1.min is not None: new_v2_min = max(v2.min, v1.min + 1) if v2.min is not None else (v1.min + 1)
        case jvm.CmpOpr.Le:
            if v2.max is not None: new_v1_max = min(v1.max, v2.max) if v1.max is not None else v2.max
            if v1.min is not None: new_v2_min = max(v2.min, v1.min) if v2.min is not None else v1.min
        case jvm.CmpOpr.Eq:
            overlap = v1 & v2
            return overlap, overlap
        case jvm.CmpOpr.Gt:
            if v2.min is not None: new_v1_min = max(v1.min, v2.min + 1) if v1.min is not None else (v2.min + 1)
            if v1.max is not None: new_v2_max = min(v2.max, v1.max - 1) if v2.max is not None else (v1.max - 1)
        case jvm.CmpOpr.Ge:
            if v2.min is not None: new_v1_min = max(v1.min, v2.min) if v1.min is not None else v2.min
            if v1.max is not None: new_v2_max = min(v2.max, v1.max) if v2.max is not None else v1.max
        case jvm.CmpOpr.Ne:
            if v1.min is not None and v1.min == v1.max == v2.min == v2.max:
                return Interval.bot(), Interval.bot()

    return Interval(new_v1_min, new_v1_max), Interval(new_v2_min, new_v2_max)

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
    # to watch for infinite loops
    all_finals = set()
    emitted = set()
    last_pc = next(iter(ai.states.keys())) # serves as anchor to ensure pc isnt unbound
    while steps > 0 and ai.worklist:
        pc, final = ai.step()
        for f in final - all_finals:  # report each outcome once, saves step budget
            jpamb.emit_step(x, pc, f, depth=1)
            all_finals.add(f)
            steps -= 1

        if pc in emitted:  # revisits add no coverage, skip to save step budget
            continue
        emitted.add(pc)
        x = jpamb.emit_step(x, pc, ai.states, depth=1)
        steps -= 1
    if not all_finals: # 
        jpamb.emit_step(x, last_pc, "*", depth=1)

def abstract_analysis_results(
    bc: jpamb.Bytecode,
    methodid: jvm.AbsMethodID,
    inputs: jpamb.Input | None = None,
) -> dict[str, list[AbstractSmith]]:
    """Run the static analysis on one method and return, for each outcome it
    can reach ("ok", "divide by zero", ...), the Smith states that lead there
    (pattern, length, cursor): one per place in the code that raises the
    outcome. Paths that meet before that place are joined into one Smith.

    "*" (may run forever) lists the Smith at each reachable back-edge target.
    A missing outcome cannot happen; if "*" is the only key, the method
    can only run forever. analyse() answers the queries from this dict.

    inputs=None analyses every input, including every bitstring.
    The Smith is bottom for methods that take no Smith.
    """
    ai = AbstractInterpreter.initial(bc, methodid, inputs)
    while ai.worklist:
        ai.step(trace=False)
    return {outcome: list(at.values()) for outcome, at in ai.outcome_smiths.items()}


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

    results = abstract_analysis_results(bc, methodid)
    for outcome, smiths in sorted(results.items()):
        for smith in smiths:
            if not smith.is_bot:
                print(f"{outcome}: {smith}", file=sys.stderr)
    for query in jpamb.QUERIES:
        print(f"{query};{answer(query, results)}")


def answer(query: str, results: dict[str, list[AbstractSmith]]) -> str:
    """Answer one jpamb query from the analysis results.

    Nothing but "*" reachable: the method can only run forever.
    Otherwise a reachable outcome (or loop, for "*") is "maybe" and a
    missing one is "no", except that when "ok" is not reachable every
    query except "*" stays "maybe", as a safety net.
    """
    reachable = set(results) - {"*"}
    if not reachable:
        return "yes" if query == "*" else "no"
    if query in results:
        return "maybe"
    if query != "*" and "ok" not in results:
        return "maybe"
    return "no"
