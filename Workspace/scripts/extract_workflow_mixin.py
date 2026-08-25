#!/usr/bin/env python3
"""Move exact method source blocks from DENTOWorkflow classes into a mixin.

This development-only utility deliberately does not rewrite method bodies.  A
span is inclusive and follows the method order in the source class.
"""

from __future__ import annotations

import argparse
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / "DENTOWorkflow" / "DENTOWorkflow.py"
PACKAGE = (
    ROOT
    / "DENTOWorkflow"
    / "Resources"
    / "Python"
    / "dentobot_workflow"
)


def class_node(source: str, name: str) -> ast.ClassDef:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise RuntimeError(f"Class not found: {name}")


def method_nodes(node: ast.ClassDef) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        child
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def method_start(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    decorator_lines = [decorator.lineno for decorator in node.decorator_list]
    return min([node.lineno, *decorator_lines])


def selected_methods(
    methods: list[ast.FunctionDef | ast.AsyncFunctionDef],
    spans: list[str],
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    positions = {method.name: index for index, method in enumerate(methods)}
    selected: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for span in spans:
        first, separator, last = span.partition(":")
        if not separator:
            last = first
        if first not in positions or last not in positions:
            raise RuntimeError(f"Unknown method span: {span}")
        first_index = positions[first]
        last_index = positions[last]
        if first_index > last_index:
            raise RuntimeError(f"Reversed method span: {span}")
        selected.extend(methods[first_index : last_index + 1])
    identities = [id(method) for method in selected]
    if len(identities) != len(set(identities)):
        raise RuntimeError("Method spans overlap")
    return sorted(selected, key=lambda method: method.lineno)


def create_runtime(source: str) -> None:
    destination = PACKAGE / "runtime.py"
    if destination.exists():
        return
    marker = "@parameterNodeWrapper"
    prelude = source[: source.index(marker)]
    old_helper = (
        '_helperDirectory = Path(__file__).resolve().parent / "Resources" / "Python"'
    )
    if old_helper not in prelude:
        raise RuntimeError("Workflow helper-path prelude changed")
    prelude = prelude.replace(
        old_helper,
        "_helperDirectory = Path(__file__).resolve().parents[1]",
    )
    destination.write_text(
        '"""Shared Slicer/runtime imports for mechanically extracted mixins.\n\n'
        "Domain modules will tighten these imports after relocation parity.\n"
        '"""\n\n'
        + prelude
        + "\n__all__ = tuple(\n"
        + "    name for name in globals() if not name.startswith(\"__\")\n"
        + ")\n",
        encoding="utf-8",
    )


def extract(args: argparse.Namespace) -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    create_runtime(source)
    owner = class_node(source, args.owner)
    methods = method_nodes(owner)
    selected = selected_methods(methods, args.span)
    if not selected:
        raise RuntimeError("No methods selected")

    destination = PACKAGE / f"{args.module}.py"
    if destination.exists():
        raise RuntimeError(f"Destination already exists: {destination}")

    lines = source.splitlines(keepends=True)
    blocks = []
    ranges = []
    for method in selected:
        start = method_start(method) - 1
        end = method.end_lineno
        blocks.append("".join(lines[start:end]).rstrip() + "\n")
        ranges.append((start, end))

    external = (
        f'"""Extracted {args.domain} methods; public APIs remain on {args.owner}."""\n\n'
        "from __future__ import annotations\n\n"
        "from .runtime import *\n\n\n"
        f"class {args.mixin}:\n"
        + "\n".join(blocks)
    )
    destination.write_text(external, encoding="utf-8")

    for start, end in sorted(ranges, reverse=True):
        del lines[start:end]
    rewritten = "".join(lines)

    class_marker = f"class {args.owner}("
    replacement = f"class {args.owner}({args.mixin}, "
    if class_marker not in rewritten:
        raise RuntimeError(f"Class declaration changed: {args.owner}")
    rewritten = rewritten.replace(class_marker, replacement, 1)

    import_line = (
        f"from dentobot_workflow.{args.module} import {args.mixin}\n\n\n"
    )
    class_position = rewritten.index(replacement)
    rewritten = rewritten[:class_position] + import_line + rewritten[class_position:]
    ast.parse(rewritten)
    ast.parse(external)
    WORKFLOW.write_text(rewritten, encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--owner", required=True)
    result.add_argument("--mixin", required=True)
    result.add_argument("--module", required=True)
    result.add_argument("--domain", required=True)
    result.add_argument("--span", action="append", required=True)
    return result


if __name__ == "__main__":
    extract(parser().parse_args())
