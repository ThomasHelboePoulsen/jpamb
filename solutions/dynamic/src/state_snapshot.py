"""Immutable execution-state keys for cycle detection."""

import struct

import jvm.state as jvmc


def stack_value_snapshot(value):
    if isinstance(value, jvmc.StackFloat):
        return (jvmc.StackFloat, struct.pack(">d", value.value))
    return value


def heap_value_snapshot(value):
    match value:
        case jvmc.HeapArray(contains=element_type, values=values):
            return (jvmc.HeapArray, element_type, tuple(values))
        case jvmc.HeapObject(classname=classname, fields=fields):
            field_values = frozenset(
                (name, stack_value_snapshot(content))
                for name, content in fields.items()
            )
            return (jvmc.HeapObject, classname, field_values)
        case jvmc.HeapString(content=content):
            return (jvmc.HeapString, content)
        case _:
            raise NotImplementedError(f"Cannot snapshot heap value {value!r}")


def state_snapshot(state: jvmc.State) -> tuple:
    frames = []
    for frame in state.frames.frames:
        operands = tuple(stack_value_snapshot(v) for v in frame.stack.operands)
        locals_ = tuple(stack_value_snapshot(v) for v in frame.locals.locals)
        frames.append((frame.pc, operands, locals_))

    heap = tuple(heap_value_snapshot(value) for value in state.heap.memory)
    return (tuple(frames), heap)
