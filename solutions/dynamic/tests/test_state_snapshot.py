from copy import deepcopy

import pytest

import jvm
import jvm.state as jvmc
from state_snapshot import state_snapshot


def make_state():
    method = jvm.AbsMethodID.decode("example.Test.run:()V")
    frames = [
        jvmc.Frame(
            jvmc.Locals([jvmc.StackInt(1), None]),
            jvmc.OperandStack.from_values([jvmc.StackInt(2)]),
            jvmc.PC(method, 0),
        )
        for _ in range(2)
    ]
    field = jvm.FieldID("count", jvm.Int())
    heap = jvmc.Heap([
        jvmc.HeapArray(jvm.Int(), [3]),
        jvmc.HeapObject(jvm.ClassName("example.Test"), {field: jvmc.StackInt(4)}),
        jvmc.HeapString("hello"),
    ])
    return jvmc.State(heap, jvmc.CallStack.from_frames(frames))


@pytest.mark.parametrize("frame_index", [0, 1])
@pytest.mark.parametrize("part", ["method", "offset", "locals", "stack"])
def test_every_frame_contributes_to_snapshot(frame_index, part):
    state = make_state()
    before = state_snapshot(state)
    frame = state.frames.frames[frame_index]
    if part == "method":
        method = jvm.AbsMethodID.decode("example.Test.other:()V")
        frame.pc = jvmc.PC(method, frame.pc.offset)
    elif part == "offset":
        frame.pc += 1
    elif part == "locals":
        frame.locals[0] = jvmc.StackInt(99)
    else:
        frame.stack.pop()
        frame.stack.push(jvmc.StackInt(99))
    assert state_snapshot(state) != before
    assert before == state_snapshot(make_state())


@pytest.mark.parametrize("part", ["array", "array_type", "field", "class", "string", "allocation"])
def test_heap_changes_do_not_look_like_cycles(part):
    state = make_state()
    before = state_snapshot(state)
    seen = {before}
    if part == "array":
        state.heap.memory[0].values[0] -= 1
    elif part == "array_type":
        state.heap.memory[0].contains = jvm.Char()
    elif part == "field":
        field = jvm.FieldID("count", jvm.Int())
        state.heap.memory[1].fields[field] = jvmc.StackInt(5)
    elif part == "class":
        state.heap.memory[1].classname = jvm.ClassName("example.Other")
    elif part == "string":
        state.heap.memory[2].content = "goodbye"
    else:
        state.heap.new(jvmc.HeapString("new"))
    assert state_snapshot(state) not in seen
    assert state_snapshot(make_state()) in seen


def test_equal_states_match_and_restored_state_is_a_cycle():
    state = make_state()
    seen = {state_snapshot(state)}
    assert state_snapshot(deepcopy(state)) in seen
    state.heap.memory[0].values[0] -= 1
    assert state_snapshot(state) not in seen
    state.heap.memory[0].values[0] += 1
    assert state_snapshot(state) in seen


def test_field_insertion_order_does_not_affect_snapshot():
    state = make_state()
    fields = state.heap.memory[1].fields
    fields[jvm.FieldID("other", jvm.Int())] = jvmc.StackInt(5)
    before = state_snapshot(state)
    state.heap.memory[1].fields = dict(reversed(list(fields.items())))
    assert state_snapshot(state) == before


def test_float_sign_and_nan_are_preserved():
    state = make_state()
    frame = state.frames.peek()
    frame.locals[0] = jvmc.StackFloat(0.0)
    positive_zero = state_snapshot(state)
    frame.locals[0] = jvmc.StackFloat(-0.0)
    assert state_snapshot(state) != positive_zero
    frame.locals[0] = jvmc.StackFloat(float("nan"))
    assert state_snapshot(state) == state_snapshot(deepcopy(state))
