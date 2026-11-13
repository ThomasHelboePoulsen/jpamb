"""Syntactic analysis using tree-sitter to inspect deterministic randomness structure.

output list of tuples [(type,start_index,end_index),...]
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import tree_sitter
import tree_sitter_java

import jpamb
import jvm

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())


@dataclass(frozen=True)
class BitField:
    """Represents a segment of bits read from Smith."""

    field_type: str  # "boolean" or "integer". might be extended with long and short etc if implemented.
    start_index: int  # Inclusive starting bit offset (e.g. 0)
    end_index: int  # Inclusive ending bit offset (e.g. 0 or 31)

    def as_tuple(self) -> tuple[str, int, int]:
        """Returns the format (type, startIndex, endIndex)."""
        return (self.field_type, self.start_index, self.end_index)


@dataclass(frozen=True)
class PathState: 
    """Represents the state of an execution path during AST traversal. 
    Similar to how static analysis is done. both possible realities are considered and executed."""

    bit_cursor: int
    bitfields: tuple[BitField, ...]  # currently found bitfields


def parse_java_source(srcfile: Path | str) -> tree_sitter.Tree:
    """Parse a Java source file using tree-sitter."""
    parser = tree_sitter.Parser(JAVA_LANGUAGE)
    content = Path(srcfile).read_bytes()
    return parser.parse(content)


def find_class_node(root: tree_sitter.Node, class_name: str) -> tree_sitter.Node:
    """Find a class declaration node matching class_name."""
    for child in root.named_children:
        if child.type == "class_declaration":
            name_node = child.child_by_field_name("name")
            if name_node and name_node.text.decode("utf-8") == class_name:
                return child
    raise ValueError(f"Could not find class {class_name}")


def find_method_node(class_node: tree_sitter.Node, method_name: str) -> tree_sitter.Node:
    """Find a method declaration node matching method_name."""
    body = class_node.child_by_field_name("body")
    if body is None:
        raise ValueError("Class has no body")
    for child in body.named_children:
        if child.type == "method_declaration":
            name_node = child.child_by_field_name("name")
            if name_node and name_node.text.decode("utf-8") == method_name:
                return child
    raise ValueError(f"Could not find method {method_name}")


def find_smith_parameter(method_node: tree_sitter.Node) -> str | None:
    """Find the variable name of the parameter with type 'Smith'."""
    params = method_node.child_by_field_name("parameters")
    if not params:
        return None
    for child in params.named_children:
        if child.type in {"formal_parameter", "spread_parameter"}:
            type_node = child.child_by_field_name("type")
            name_node = child.child_by_field_name("name")
            if type_node and "Smith" in type_node.text.decode("utf-8"):
                return name_node.text.decode("utf-8") if name_node else None
    return None


def get_class_methods(class_node: tree_sitter.Node) -> dict[str, tree_sitter.Node]:
    """Index all methods in the class by method name."""
    methods = {}
    body = class_node.child_by_field_name("body")
    if body:
        for child in body.named_children:
            if child.type == "method_declaration":
                name = child.child_by_field_name("name")
                if name:
                    methods[name.text.decode("utf-8")] = child
    return methods


def explore_branch(
    node: tree_sitter.Node,
    smith_var_name: str,
    class_methods: dict[str, tree_sitter.Node],
    states: list[PathState],
    visited_methods: set[str],
) -> list[PathState]:
    """Explores both branches of an if-statement or ternary expression."""
    cond = node.child_by_field_name("condition")
    then_node = node.child_by_field_name("consequence")
    else_node = node.child_by_field_name("alternative")

    states_after_cond = (
        execute_node_paths(cond, smith_var_name, class_methods, states, visited_methods)
        if cond
        else states
    )
    states_then = (
        execute_node_paths(then_node, smith_var_name, class_methods, states_after_cond, visited_methods)
        if then_node
        else states_after_cond
    )
    states_else = (
        execute_node_paths(else_node, smith_var_name, class_methods, states_after_cond, visited_methods)
        if else_node
        else states_after_cond
    )
    return states_then + states_else


def explore_loop(
    node: tree_sitter.Node,
    smith_var_name: str,
    class_methods: dict[str, tree_sitter.Node],
    states: list[PathState],
    visited_methods: set[str],
) -> list[PathState]:
    """Explores loop paths: one path skipping the loop, one path entering one iteration."""
    cond = node.child_by_field_name("condition")
    body = node.child_by_field_name("body")

    states_after_cond = (
        execute_node_paths(cond, smith_var_name, class_methods, states, visited_methods=visited_methods)
        if cond
        else states
    )
    states_skip = states_after_cond
    states_iter = (
        execute_node_paths(body, smith_var_name, class_methods, states_after_cond, visited_methods=visited_methods)
        if body
        else states_after_cond
    )
    return states_skip + states_iter


def explore_smith_draw(
    args: tree_sitter.Node | None,
    states: list[PathState],
) -> list[PathState]:
    """Handles direct calls to smith.draw() (boolean) or smith.draw(bits) (integer)."""
    arg_list = args.named_children if args else []
    new_states: list[PathState] = []

    for state in states:
        cur = state.bit_cursor
        if not arg_list:
            # boolean (1 bit)
            field = BitField(
                field_type="boolean",
                start_index=cur,
                end_index=cur,
            )
            new_states.append(PathState(cur + 1, state.bitfields + (field,)))
        else:
            # integer (n bits)
            try:
                bits = int(arg_list[0].text.decode("utf-8"))
            except (ValueError, AttributeError):
                bits = 32
            field = BitField(
                field_type="integer",
                start_index=cur,
                end_index=cur + bits - 1,
            )
            new_states.append(PathState(cur + bits, state.bitfields + (field,)))

    return new_states


def explore_callee_invocation(
    call_name: str,
    args: tree_sitter.Node | None,
    smith_var_name: str,
    class_methods: dict[str, tree_sitter.Node],
    states: list[PathState],
    visited_methods: set[str],
) -> list[PathState] | None:
    """Explores internal helper method calls when smith is passed as an argument."""
    callee_args = [
        c.text.decode("utf-8")
        for c in (args.named_children if args else [])
    ]
    if smith_var_name in callee_args and call_name not in visited_methods:
        callee_node = class_methods[call_name]
        c_smith = find_smith_parameter(callee_node)
        if c_smith:
            callee_body = callee_node.child_by_field_name("body")
            if callee_body:
                return execute_node_paths(
                    callee_body,
                    c_smith,
                    class_methods,
                    states,
                    visited_methods=visited_methods | {call_name},
                )
    return None


def explore_method_invocation(
    node: tree_sitter.Node,
    smith_var_name: str,
    class_methods: dict[str, tree_sitter.Node],
    states: list[PathState],
    visited_methods: set[str],
) -> list[PathState]:
    """Dispatches method invocations: direct smith.draw, callee methods, or general calls."""
    obj = node.child_by_field_name("object")
    name = node.child_by_field_name("name")
    args = node.child_by_field_name("arguments")

    obj_name = obj.text.decode("utf-8") if obj else None
    call_name = name.text.decode("utf-8") if name else None

    # 1. Direct smith.draw() call
    if obj_name == smith_var_name and call_name == "draw":
        return explore_smith_draw(args, states)

    # 2. Smith passed to an internal helper method
    if (obj is None or obj_name == "this") and call_name in class_methods:
        callee_result = explore_callee_invocation(
            call_name, args, smith_var_name, class_methods, states, visited_methods
        )
        if callee_result is not None:
            return callee_result

    # 3. Default: recurse into children
    cur_states = states
    for child in node.named_children:
        cur_states = execute_node_paths(
            child, smith_var_name, class_methods, cur_states, visited_methods
        )
    return cur_states


def execute_node_paths(
    node: tree_sitter.Node,
    smith_var_name: str,
    class_methods: dict[str, tree_sitter.Node],
    states: list[PathState],
    visited_methods: set[str] | None = None,
) -> list[PathState]:
    """Traverse an AST node over multiple path states, forking on branches.

    Returns the list of all surviving PathStates at the end of this node.
    """
    if visited_methods is None:
        visited_methods = set()
    if not states:
        return []

    match node.type:
        case "if_statement" | "ternary_expression":
            return explore_branch(node, smith_var_name, class_methods, states, visited_methods)

        case "while_statement" | "for_statement" | "do_statement" | "enhanced_for_statement":
            return explore_loop(node, smith_var_name, class_methods, states, visited_methods)

        case "method_invocation":
            return explore_method_invocation(node, smith_var_name, class_methods, states, visited_methods)

        case _:
            cur_states = states
            for child in node.named_children:
                cur_states = execute_node_paths(
                    child, smith_var_name, class_methods, cur_states, visited_methods
                )
            return cur_states


def get_bitstring_paths(
    class_node: tree_sitter.Node,
    method_node: tree_sitter.Node,
) -> list[list[BitField]]:
    """Extracts the list of BitFields for each explored control-flow path."""
    smith_var_name = find_smith_parameter(method_node)
    if not smith_var_name:
        return []

    body = method_node.child_by_field_name("body")
    if not body:
        return []

    class_methods = get_class_methods(class_node)
    initial_states = [PathState(bit_cursor=0, bitfields=())]
    final_states = execute_node_paths(body, smith_var_name, class_methods, initial_states)

    return [list(state.bitfields) for state in final_states]


def get_bitstring_fields(
    methodid: jvm.AbsMethodID,
    suite: jpamb.Suite,
) -> list[BitField]:
    """Returns the union of all BitField interpretations across all reachable paths."""
    srcfile = suite.sourcefile(methodid.classname)
    tree = parse_java_source(srcfile)
    class_name = str(methodid.classname.name)
    class_node = find_class_node(tree.root_node, class_name)
    method_name = methodid.extension.name
    method_node = find_method_node(class_node, method_name)

    paths = get_bitstring_paths(class_node, method_node)

    
    unique_fields: set[BitField] = set()
    for path in paths:
        for field in path:
            unique_fields.add(field)

    return sorted(unique_fields, key=lambda f: (f.start_index, f.end_index))


def get_bitstring_structure(
    methodid: jvm.AbsMethodID,
    suite: jpamb.Suite,
) -> list[tuple[str, int, int]]:
    """returns the union of (type, startIndex, endIndex) across all paths."""
    fields = get_bitstring_fields(methodid, suite)
    return [field.as_tuple() for field in fields]
