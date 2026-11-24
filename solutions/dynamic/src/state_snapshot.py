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


def frame_snapshot(frame: jvmc.Frame) -> tuple:
    operands = tuple(stack_value_snapshot(v) for v in frame.stack.operands)
    locals_ = tuple(stack_value_snapshot(v) for v in frame.locals.locals)
    return (frame.pc, operands, locals_)


def heap_snapshot(state: jvmc.State) -> tuple:
    return tuple(heap_value_snapshot(value) for value in state.heap.memory)


def state_snapshot(state: jvmc.State) -> tuple:
    return (tuple(map(frame_snapshot, state.frames.frames)), heap_snapshot(state))


class ExecutionSnapshots:
    """Snapshot successive nonterminal states from one execution.

    Only the top frame can change between instructions. Compare keys
    produced by the same instance.
    """

    def __init__(self):
        self._caller_ids: dict[tuple[int, tuple], int] = {}
        self._caller_prefixes = [0]

    def snapshot(self, state: jvmc.State) -> tuple:
        frames = state.frames.frames
        depth = len(frames)
        del self._caller_prefixes[depth:]
        # Intern the exact stack prefix. Suspended callers stay unchanged
        # until control returns to them.
        while len(self._caller_prefixes) < depth:
            caller_index = len(self._caller_prefixes) - 1
            caller = (self._caller_prefixes[-1], frame_snapshot(frames[caller_index]))
            caller_id = self._caller_ids.setdefault(caller, len(self._caller_ids) + 1)
            self._caller_prefixes.append(caller_id)
        return (self._caller_prefixes[-1], frame_snapshot(frames[-1]), heap_snapshot(state))
