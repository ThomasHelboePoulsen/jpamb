"""Syntactic analysis using tree-sitter to inspect deterministic randomness structure.

Extracts the union of all reachable bit intervals consumed from `Smith`,
exploring branches (if/else, ternaries, and loops) across multiple control-flow paths.

Produces a deduplicated union list such as:
    [("boolean", 0, 0), ("integer", 1, 32), ("boolean", 33, 33)]
to guide structure-aware, coverage-based fuzzing on bitstrings.
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
    bits: int  # Total number of bits in this segment
    in_loop: bool = False  # True if draw occurs inside a loop
    source_call: str = ""  # Source code representation, e.g. "smith.draw(4)"

    def as_tuple(self) -> tuple[str, int, int]:
        """Returns the format (type, startIndex, endIndex)."""
        return (self.field_type, self.start_index, self.end_index)


@dataclass(frozen=True)
class PathState: 
    """Represents the state of an execution path during AST traversal. 
    Similar to how static analysis is done. both possible realities are considered and executed."""

    current_bit: int
    fields: tuple[BitField, ...] # currently found bitfields


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


def execute_node_paths(
    node: tree_sitter.Node,
    smith_var: str,
    class_methods: dict[str, tree_sitter.Node],
    states: list[PathState],
    in_loop: bool = False,
    visited_methods: set[str] | None = None,
) -> list[PathState]:
    """Traverse an AST node over multiple path states, forking on branches.

    Returns the list of all surviving PathStates at the end of this node.
    """
    if visited_methods is None:
        visited_methods = set()
    if not states:
        return []

    
    if node.type == "if_statement":
        cond = node.child_by_field_name("condition")
        then_node = node.child_by_field_name("consequence")
        else_node = node.child_by_field_name("alternative")

        # execute the condition check. 
        states_after_cond = (
            execute_node_paths(
                cond, smith_var, class_methods, states, in_loop, visited_methods
            )
            if cond
            else states # malformed, return early. 
        )

        # execute the consequences branch. 
        states_then = (
            execute_node_paths(
                then_node,
                smith_var,
                class_methods,
                states_after_cond,
                in_loop,
                visited_methods,
            )
            if then_node
            else states_after_cond
        )

        # execute the alternative branch.
        if else_node:
            states_else = execute_node_paths(
                else_node,
                smith_var,
                class_methods,
                states_after_cond,
                in_loop,
                visited_methods,
            )
        else:
            states_else = states_after_cond

        # return all possible states. 
        return states_then + states_else

    # same as above, just with ternary. 
    if node.type == "ternary_expression":
        cond = node.child_by_field_name("condition")
        then_node = node.child_by_field_name("consequence")
        else_node = node.child_by_field_name("alternative")

        states_after_cond = (
            execute_node_paths(
                cond, smith_var, class_methods, states, in_loop, visited_methods
            )
            if cond
            else states
        )
        states_then = (
            execute_node_paths(
                then_node,
                smith_var,
                class_methods,
                states_after_cond,
                in_loop,
                visited_methods,
            )
            if then_node
            else states_after_cond
        )
        states_else = (
            execute_node_paths(
                else_node,
                smith_var,
                class_methods,
                states_after_cond,
                in_loop,
                visited_methods,
            )
            if else_node
            else states_after_cond
        )
        return states_then + states_else

    # looping. same as above. there is condition and then consequence and alternative. 
    if node.type in {
        "while_statement",
        "for_statement",
        "do_statement",
        "enhanced_for_statement",
    }:
        cond = node.child_by_field_name("condition")
        body = node.child_by_field_name("body")

        states_after_cond = (
            execute_node_paths(
                cond, smith_var, class_methods, states, in_loop=True, visited_methods=visited_methods
            )
            if cond
            else states
        )

        # alternative. i.e. loop was skipped. 
        states_skip = states_after_cond

        # consequence. sets "in loop" to true. 
        states_iter = (
            execute_node_paths(
                body,
                smith_var,
                class_methods,
                states_after_cond,
                in_loop=True,
                visited_methods=visited_methods,
            )
            if body
            else states_after_cond
        )

        return states_skip + states_iter

    # basecase, checks for calls to smith, or passing of smith.
    if node.type == "method_invocation":
        obj = node.child_by_field_name("object")
        name = node.child_by_field_name("name")
        args = node.child_by_field_name("arguments")

        obj_name = obj.text.decode("utf-8") if obj else None
        call_name = name.text.decode("utf-8") if name else None

        # direct call
        if obj_name == smith_var and call_name == "draw":
            arg_list = args.named_children if args else []
            new_states: list[PathState] = []
            for st in states:
                cur = st.current_bit
                if not arg_list:
                    # boolean (1 bit)
                    field = BitField(
                        field_type="boolean",
                        start_index=cur,
                        end_index=cur,
                        bits=1,
                        in_loop=in_loop,
                        source_call=node.text.decode("utf-8"),
                    )
                    new_states.append(PathState(cur + 1, st.fields + (field,)))
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
                        bits=bits,
                        in_loop=in_loop,
                        source_call=node.text.decode("utf-8"),
                    )
                    new_states.append(PathState(cur + bits, st.fields + (field,)))
            return new_states

        # smith is passed to another method.
        if (obj is None or obj_name == "this") and call_name in class_methods:
            callee_args = [
                c.text.decode("utf-8")
                for c in (args.named_children if args else [])
            ]
            if smith_var in callee_args and call_name not in visited_methods:
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
                            in_loop=in_loop,
                            visited_methods=visited_methods | {call_name},
                        )

    # default recurses. Just recurses over all children.
    cur_states = states
    for child in node.named_children:
        cur_states = execute_node_paths(
            child, smith_var, class_methods, cur_states, in_loop, visited_methods
        )
    return cur_states


def get_bitstring_paths(
    class_node: tree_sitter.Node,
    method_node: tree_sitter.Node,
) -> list[list[BitField]]:
    """Extracts the list of BitFields for each explored control-flow path."""
    smith_var = find_smith_parameter(method_node)
    if not smith_var:
        return []

    body = method_node.child_by_field_name("body")
    if not body:
        return []

    class_methods = get_class_methods(class_node)
    initial_states = [PathState(current_bit=0, fields=())]
    final_states = execute_node_paths(body, smith_var, class_methods, initial_states)

    return [list(st.fields) for st in final_states]


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
