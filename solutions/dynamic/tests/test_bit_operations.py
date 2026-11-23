import pytest

import jvm
import jvm.state as jvmc
from dynamic import step


@pytest.mark.parametrize(
    "value, shift, expected",
    [
        (-8, 1, 2147483644),
        (-1, 1, 2147483647),
        (-2147483648, 1, 1073741824),
        (-1, 31, 1),
        (-1, 0, -1),
        (-2147483648, 0, -2147483648),
        (-1, 32, -1),
        (-1, 33, 2147483647),
        (-1, -1, 1),
        (-1, -32, -1),
        (6, 1, 3),
        (0, 31, 0),
    ],
)
def test_unsigned_right_shift(value, shift, expected):
    method = jvm.AbsMethodID.decode("example.Test.run:()V")
    pc = jvmc.PC(method, 0)
    frame = jvmc.Frame(
        jvmc.Locals([]),
        jvmc.OperandStack.from_values(
            [jvmc.StackInt(123), jvmc.StackInt(value), jvmc.StackInt(shift)]
        ),
        pc,
    )
    state = jvmc.State(jvmc.Heap(), jvmc.CallStack.from_frames([frame]))
    bytecode = {
        pc: jvm.Opcode.from_json(
            {"opr": "bitopr", "offset": 0, "type": "int", "operant": "ushr"}
        )
    }

    executed_pc, result = step(bytecode, state)

    assert result is state
    assert executed_pc == pc
    assert frame.pc == pc + 1
    assert list(frame.stack.operands) == [jvmc.StackInt(123), jvmc.StackInt(expected)]


@pytest.mark.parametrize(
    "content,index,expected",
    [
        ("1001", 0, ord("1")),
        ("1001", 3, ord("1")),
        ("1001", 4, None),
        ("1001", -1, None),
    ],
)
def test_string_char_at(content, index, expected):
    method = jvm.AbsMethodID.decode("example.Test.run:()V")
    pc = jvmc.PC(method, 0)
    frame = jvmc.Frame(
        jvmc.Locals([]),
        jvmc.OperandStack.from_values([]),
        pc,
    )
    state = jvmc.State(jvmc.Heap(), jvmc.CallStack.from_frames([frame]))
    string_ref = state.heap.new(jvmc.HeapString(content))
    frame.stack.push(string_ref)
    frame.stack.push(jvmc.StackInt(index))
    bytecode = {
        pc: jvm.InvokeVirtual(
            offset=0,
            method=jvm.AbsMethodID.decode("java.lang.String.charAt:(I)C"),
        )
    }

    executed_pc, result = step(bytecode, state)

    assert executed_pc == pc
    if expected is None:
        assert result == "out of bounds"
        assert frame.pc == pc
    else:
        assert result is state
        assert frame.pc == pc + 1
        assert list(frame.stack.operands) == [jvmc.StackInt(expected)]
