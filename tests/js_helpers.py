"""Shared helpers for the tests that run real first-party JS through node."""

def _extract_js_function(source, name):
    """Return the source text of `function <name>(...) { ... }`, brace-matched.

    Skips braces inside strings, template literals and comments so a function
    body containing `${...}` or `{` in a string does not truncate the match.
    """
    start = source.find(f"function {name}")
    if start == -1:
        raise AssertionError(f"function {name} not found")

    depth = 0
    started = False
    i = start
    in_single = in_double = in_template = False
    in_line_comment = in_block_comment = False

    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
        elif in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 1
        elif in_single or in_double or in_template:
            if ch == "\\":
                i += 1
            elif in_single and ch == "'":
                in_single = False
            elif in_double and ch == '"':
                in_double = False
            elif in_template and ch == "`":
                in_template = False
        elif ch == "/" and nxt == "/":
            in_line_comment = True
            i += 1
        elif ch == "/" and nxt == "*":
            in_block_comment = True
            i += 1
        elif ch == "'":
            in_single = True
        elif ch == '"':
            in_double = True
        elif ch == "`":
            in_template = True
        elif ch == "{":
            depth += 1
            started = True
        elif ch == "}":
            depth -= 1
            if started and depth == 0:
                return source[start:i + 1]
        i += 1

    raise AssertionError(f"unbalanced braces extracting {name}")
