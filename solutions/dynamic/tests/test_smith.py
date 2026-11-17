"""Smith reads must match Java's zero padding, cursor and signed int behavior."""
import importlib

import pytest
import jvm
import jvm.state as jvmc


@pytest.mark.parametrize("module", ["dynamic", "dynamic_coverage"])
@pytest.mark.parametrize("bits", ["", "0", "1", "01", "1" * 32, "1" + "0" * 31 + "1"])
def test_smith_reads(module, bits):
    interpreter = importlib.import_module(module)
    state = jvmc.State(jvmc.Heap(), jvmc.CallStack())
    bits_ref = state.heap.new(jvmc.HeapString(bits))
    index_field = jvm.FieldID("index", jvm.Int())
    ref = state.heap.new(jvmc.HeapObject(jvm.ClassName("jpamb.utils.Smith"), {
        jvm.FieldID("bits", jvm.Object(jvm.ClassName("java.lang.String"))): bits_ref,
        index_field: jvmc.StackInt(0),
    }))
    index = 0
    for count in [0, 32, 32, 1, 4]:
        padded = bits[index:index + count].ljust(count, "0")
        expected = int(padded or "0", 2)
        if expected >= 2**31:
            expected -= 2**32
        assert interpreter.draw_int(state, ref, count) == expected
        index = min(index + count, len(bits))
        assert state.heap[ref].fields[index_field].value == index
    assert interpreter.draw_bit(state, ref) is False
    assert state.heap[ref].fields[index_field].value == index


@pytest.mark.parametrize("module", ["dynamic", "dynamic_coverage"])
def test_boolean_then_partial_integer(module):
    interpreter = importlib.import_module(module)
    state = jvmc.State(jvmc.Heap(), jvmc.CallStack())
    bits_ref = state.heap.new(jvmc.HeapString("110"))
    ref = state.heap.new(jvmc.HeapObject(jvm.ClassName("jpamb.utils.Smith"), {
        jvm.FieldID("bits", jvm.Object(jvm.ClassName("java.lang.String"))): bits_ref,
        jvm.FieldID("index", jvm.Int()): jvmc.StackInt(0),
    }))
    assert interpreter.draw_bit(state, ref) is True
    assert interpreter.draw_int(state, ref, 4) == 8
    assert interpreter.draw_bit(state, ref) is False
