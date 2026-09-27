"""Find Java method literals and convert them into Python value pools."""

from collections import defaultdict
import itertools
from pathlib import Path
import random

import tree_sitter
import tree_sitter_java

import jpamb
import jvm

JAVA_LANGUAGE = tree_sitter.Language(tree_sitter_java.language())

INT_MIN = -(1 << 31)
INT_MAX = (1 << 31) - 1


def integer_candidates(literals, *, for_array=False):
    if for_array:
        values = {0, 1, -1, -(1 << 31), (1 << 31) - 1}
    else:
        values = {0, 1, -1, -(1 << 31), (1 << 31) - 1, 8}
        values.update(range(-2, 11))
    for value in literals.get(int, []):
        values.update([value - 1, value, value + 1])
    if for_array:
        values.update(random.randint(INT_MIN, INT_MAX) for _ in range(3))
    return [value for value in values if INT_MIN <= value <= INT_MAX]


def string_candidates(literals):
    values = {"", "a"}
    values.update(literals.get(str, []))
    return list(values)


def character_candidates(literals):
    characters = {'\x00', 'a', '\uffff'}
    for text in literals.get(str, []):
        if len(text) == 1:
            characters.add(text)
    for _ in range(3):
        characters.add(chr(random.randint(32, 126)))
    return list(characters)


def repeated_arrays(element_type, values):
    arrays = []
    for value in values:
        arrays.append(jpamb.case.Array(element_type, [value]))
        arrays.append(jpamb.case.Array(element_type, [value, value, value]))
    return arrays


def random_arrays(element_type, values):
    arrays = []
    for _ in range(5):
        length = random.randint(2, 10)
        contents = random.choices(values, k=length)
        arrays.append(jpamb.case.Array(element_type, contents))
    return arrays


def literal_character_arrays(raw_literals):
    arrays = []
    raw_characters = raw_literals.get("character_literal", [])
    converted = convert_literals({"character_literal": raw_characters})
    characters = converted.get(str, [])
    if characters:
        arrays.append(jpamb.case.Array(jvm.Char(), characters))
        arrays.append(jpamb.case.Array(jvm.Char(), list(reversed(characters))))

    raw_strings = raw_literals.get("string_literal", [])
    converted = convert_literals({"string_literal": raw_strings})
    for text in converted.get(str, []):
        arrays.append(jpamb.case.Array(jvm.Char(), list(text)))
    return arrays


def array_candidates(element_type, literals, raw_literals):
    match element_type:
        case jvm.Int():
            values = integer_candidates(literals, for_array=True)
        case jvm.Char():
            values = character_candidates(literals)
        case jvm.Object(jvm.ClassName("java.lang.String")):
            values = string_candidates(literals)
        case _:
            raise NotImplementedError(f"No array candidates for {element_type}")

    arrays = [jpamb.case.Array(element_type, [])]
    if element_type == jvm.Char():
        arrays.extend(literal_character_arrays(raw_literals))
    arrays.extend(repeated_arrays(element_type, values))
    arrays.extend(random_arrays(element_type, values))
    return arrays


def parameter_candidates(parameter_type, literals, raw_literals):
    match parameter_type:
        case jvm.Int():
            return [jpamb.case.Int(value) for value in integer_candidates(literals)]
        case jvm.Boolean():
            return [jpamb.case.Boolean(True), jpamb.case.Boolean(False)]
        case jvm.Object(jvm.ClassName("java.lang.String")):
            return [jpamb.case.String(value) for value in string_candidates(literals)]
        case jvm.Array(contains=element_type):
            return array_candidates(element_type, literals, raw_literals)
        case _:
            raise NotImplementedError(f"No input candidates for {parameter_type}")


def generate_inputs_from_dict(methodid, suite, max_combinations=2000):
    raw_literals = get_literals_in_method(methodid, suite)
    literals = convert_literals(raw_literals)
    pools = []
    for parameter_type in methodid.extension.params:
        pools.append(parameter_candidates(parameter_type, literals, raw_literals))

    for count, combination in enumerate(itertools.product(*pools)):
        if count >= max_combinations:
            break
        yield jpamb.case.Input(list(combination))


def convert_literals(raw_literals: dict[str, list[bytes]]) -> dict[type, list]:
    """Convert the literal forms used in cases/jpamb/cases into Python pools.

    Characters and strings share the str pool. Each integer contributes both
    signs, since unary operators are not part of the collected literals.
    Other literal forms raise NotImplementedError so support can be added
    when a test case needs it.
    """
    literals = defaultdict(list)
    for category, values in raw_literals.items():
        for raw_value in values:
            text = raw_value.decode("utf-8")
            if category == "decimal_integer_literal":
                value = int(text)
            elif category in {"string_literal", "character_literal"}:
                if text.startswith('"""') or "\\" in text:
                    raise NotImplementedError("Escaped literals and text blocks are not supported")
                value = text[1:-1]
            elif category in {"true", "false"}:
                value = category == "true"
            elif category == "null_literal":
                value = None
            else:
                raise NotImplementedError(f"Unsupported literal category: {category}")
            literals[type(value)].append(value)

    integers = set(literals[int])
    literals[int] = sorted(integers | {-value for value in integers})
    return dict(literals)


def parse_java_source(srcfile: Path) -> tree_sitter.Tree:
    parser = tree_sitter.Parser(JAVA_LANGUAGE)
    return parser.parse(srcfile.read_bytes())


def find_class(root: tree_sitter.Node, class_name: str) -> tree_sitter.Node:
    class_q = tree_sitter.Query(
        JAVA_LANGUAGE,
        f"""
        (class_declaration
            name: ((identifier) @class-name
                   (#eq? @class-name "{class_name}"))) @class
        """,
    )
    class_matches = tree_sitter.QueryCursor(class_q).captures(root).get("class", [])
    if len(class_matches) != 1:
        raise ValueError(
            f"Expected one class named {class_name}, "
            f"found {len(class_matches)}"
        )
    return class_matches[0]


def find_method(class_node: tree_sitter.Node, methodid: jvm.AbsMethodID) -> tree_sitter.Node:
    """Find a directly declared method by name and arity; reject ambiguous overloads."""
    simple_classname = str(methodid.classname.name)
    class_body = class_node.child_by_field_name("body")
    if class_body is None:
        raise ValueError(f"Class {simple_classname} has no body")

    method_name = methodid.extension.name
    method_matches = []
    for candidate in class_body.named_children:
        if candidate.type != "method_declaration":
            continue
        name_node = candidate.child_by_field_name("name")
        if name_node is None or name_node.text != method_name.encode("utf-8"):
            continue

        parameters = candidate.child_by_field_name("parameters")
        if parameters is None:
            continue
        parameter_count = sum(
            child.type in {"formal_parameter", "spread_parameter"}
            for child in parameters.named_children
        )
        if parameter_count == len(methodid.extension.params):
            method_matches.append(candidate)

    if len(method_matches) != 1:
        raise ValueError(
            f"Expected one method named {method_name} with "
            f"{len(methodid.extension.params)} parameters in {simple_classname}, "
            f"found {len(method_matches)}"
        )
    return method_matches[0]


def collect_literals(root: tree_sitter.Node) -> dict[str, list[bytes]]:
    """Group literal source text by syntax category, preserving traversal order."""
    literals: dict[str, list[bytes]] = defaultdict(list)

    def visit(node: tree_sitter.Node):
        if "literal" in node.type or node.type in {"true", "false"}:
            literals[node.type].append(node.text)

        for child in node.named_children:
            visit(child)

    visit(root)
    return literals


def get_literals_in_method(
    methodid: jvm.AbsMethodID, suite: jpamb.Suite
) -> dict[str, list[bytes]]:
    """Locate the requested method and collect its raw literals for conversion."""
    srcfile = suite.sourcefile(methodid.classname).relative_to(Path.cwd())
    tree = parse_java_source(srcfile)
    class_node = find_class(tree.root_node, str(methodid.classname.name))
    method_node = find_method(class_node, methodid)
    body = method_node.child_by_field_name("body")
    if body is None:
        raise ValueError(f"Method {methodid.extension.name} has no body")
    return collect_literals(body)
