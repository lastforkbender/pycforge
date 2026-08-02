"""Independent non-executing grammar check for PyCForge's emitted C subset.

This module intentionally does not import the C IR model or renderer.  It lexes
and parses the rendered source as a separate acceptance boundary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pycforge.converter.contracts.identifiers import (
    C11_EXTERNAL_IDENTIFIERS as _C11_EXTERNAL_IDENTIFIERS,
    C_KEYWORDS as _C_KEYWORDS,
    TARGET_RESERVED_NAMES as _TARGET_RESERVED_NAMES,
)


_TOKEN = re.compile(
    r"""
    (?P<space>\s+)
  | (?P<include>\#[ \t]*include[ \t]*(?:<[^>\n]+>|"[^"\n]+"))
  | (?P<string>"(?:[^"\\\n]|\\(?:x[0-9A-Fa-f]+|[0-7]{1,3}|.))*")
  | (?P<float>(?:(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[0-9]+[eE][+-]?[0-9]+))
  | (?P<int>(?:0|[1-9][0-9]*)(?:ULL|LLU|UL|LU|LL|L|U)?)
  | (?P<identifier>[A-Za-z_][A-Za-z0-9_]*)
  | (?P<operator>->|==|!=|<=|>=|<<|>>|&&|\|\||[{}\[\]();,.=*+\-/%<>!~&|^])
    """,
    re.VERBOSE,
)

_BASE_TYPES = {"void","char","int","long","int8_t","uint8_t","int16_t","uint16_t","int32_t","uint32_t","int64_t","uint64_t","bool","double"}
_QUALIFIERS = {"const", "volatile"}
_STORAGE = {"static", "extern"}
_REGISTERED_HEADERS = {"stdint.h", "stdbool.h"}
_STDINT_BASES = {"int8_t","uint8_t","int16_t","uint16_t","int32_t","uint32_t","int64_t","uint64_t"}
_BINARY_PRECEDENCE = {
    "||": 1, "&&": 2, "|": 3, "^": 4, "&": 5,
    "==": 6, "!=": 6, "<": 7, "<=": 7, ">": 7, ">=": 7,
    "<<": 8, ">>": 8, "+": 9, "-": 9, "*": 10, "/": 10, "%": 10,
}


@dataclass(frozen=True, slots=True)
class CTextConformanceResult:
    accepted: bool
    message: str
    token_count: int


class _ParseError(ValueError):
    pass


class _Parser:
    def __init__(self, tokens: tuple[str, ...]) -> None:
        self.tokens = tokens
        self.position = 0
        self.headers: set[str] = set()
        self.used_bases: set[str] = set()
        self.record_types: set[str] = set()

    def parse(self) -> None:
        while self._peek().startswith("#"):
            match = re.fullmatch(r"\#[ \t]*include[ \t]*<([^>\n]+)>", self._peek())
            if not match or match.group(1) not in _REGISTERED_HEADERS:
                raise _ParseError("unregistered or non-system include")
            if match.group(1) in self.headers:
                raise _ParseError(f"duplicate include: {match.group(1)}")
            self.headers.add(match.group(1))
            self.position += 1
        while self._peek():
            if self._peek().startswith("#"):
                raise _ParseError("include outside translation-unit prefix")
            self._external()
        if self.used_bases & _STDINT_BASES and "stdint.h" not in self.headers:
            raise _ParseError("fixed-width integer type without stdint.h")
        if "bool" in self.used_bases and "stdbool.h" not in self.headers:
            raise _ParseError("Boolean type or literal without stdbool.h")

    def _external(self) -> None:
        if self._peek() == "typedef":
            self._record_definition()
            return
        self._storage()
        self._type(allow_void=True)
        self._identifier(file_scope=True)
        if self._accept("("):
            self._parameters()
            self._expect(")")
            if self._accept(";"):
                return
            self._block()
            return
        self._array_suffix()
        if self._accept("="):
            self._initializer()
        self._expect(";")

    def _record_definition(self) -> None:
        self._expect("typedef")
        self._expect("struct")
        tag = self._identifier(file_scope=True)
        self._expect("{")
        fields: set[str] = set()
        while self._peek() != "}":
            if not self._peek():
                raise _ParseError("unclosed record definition")
            self._type()
            field = self._identifier()
            if field in fields:
                raise _ParseError(f"duplicate record field: {field}")
            fields.add(field)
            self._expect(";")
        if not fields:
            raise _ParseError("empty record definition")
        self._expect("}")
        alias = self._identifier(file_scope=True)
        if alias != tag:
            raise _ParseError("record tag and typedef name must match")
        if alias in self.record_types:
            raise _ParseError(f"duplicate record type: {alias}")
        self.record_types.add(alias)
        self._expect(";")

    def _parameters(self) -> None:
        if self._peek() == ")":
            raise _ParseError("empty C parameter list must be written as void")
        if self._peek() == "void" and self._peek(1) == ")":
            self.position += 1
            return
        first = True
        while self._peek() != ")":
            if not first:
                self._expect(",")
            self._type()
            self._identifier()
            first = False

    def _block(self) -> None:
        self._expect("{")
        while self._peek() != "}":
            if not self._peek():
                raise _ParseError("unclosed block")
            self._statement()
        self._expect("}")

    def _statement(self) -> None:
        token = self._peek()
        if token == "return":
            self.position += 1
            if self._peek() != ";": self._expression()
            self._expect(";")
            return
        if token in {"break", "continue"}:
            self.position += 1; self._expect(";"); return
        if token == "if":
            self.position += 1; self._expect("("); self._expression(); self._expect(")"); self._block()
            if self._accept("else"): self._block()
            return
        if token == "while":
            self.position += 1; self._expect("("); self._expression(); self._expect(")"); self._block(); return
        if token == "for":
            self.position += 1; self._expect("(")
            self._storage(); self._type(); self._identifier(); self._expect("="); self._expression(); self._expect(";")
            self._expression(); self._expect(";")
            self._expression(); self._expect("="); self._expression(); self._expect(")"); self._block(); return
        if self._declaration_start():
            self._storage(); self._type(); self._identifier(); self._array_suffix()
            if self._accept("="): self._initializer()
            self._expect(";")
            return
        self._expression()
        if self._accept("="): self._expression()
        self._expect(";")

    def _expression(self, minimum: int = 1) -> None:
        self._unary()
        while self._peek() in _BINARY_PRECEDENCE and _BINARY_PRECEDENCE[self._peek()] >= minimum:
            precedence = _BINARY_PRECEDENCE[self._peek()]
            self.position += 1
            self._expression(precedence + 1)

    def _unary(self) -> None:
        if self._peek() in {"-", "+", "!", "~", "&", "*"}:
            self.position += 1; self._unary(); return
        self._primary()

    def _primary(self) -> None:
        token = self._peek()
        if token == "(":
            self.position += 1; self._expression(); self._expect(")")
        elif token.startswith('"') or token in {"true", "false"} or re.fullmatch(r"(?:[0-9].*|\.[0-9].*)", token):
            if token in {"true", "false"}: self.used_bases.add("bool")
            self.position += 1
        elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            self.position += 1
        else:
            raise _ParseError(f"expected expression, found {token or 'end of input'}")
        while True:
            if self._accept("("):
                if self._peek() != ")":
                    self._expression()
                    while self._accept(","): self._expression()
                self._expect(")")
            elif self._accept("["):
                self._expression(); self._expect("]")
            elif self._accept(".") or self._accept("->"):
                self._identifier()
            else:
                break

    def _initializer(self) -> None:
        if not self._accept("{"):
            self._expression()
            return
        if self._peek() == "}":
            raise _ParseError("empty initializer list")
        self._expression()
        while self._accept(","):
            self._expression()
        self._expect("}")

    def _array_suffix(self) -> None:
        while self._accept("["):
            token = self._peek()
            if not re.fullmatch(r"(?:0|[1-9][0-9]*)", token):
                raise _ParseError("array extent must be an unsuffixed decimal integer")
            self.position += 1
            self._expect("]")

    def _type(self, *, allow_void: bool = False) -> None:
        while self._peek() in _QUALIFIERS: self.position += 1
        base = self._peek()
        if base not in _BASE_TYPES | self.record_types or (base == "void" and not allow_void):
            raise _ParseError(f"expected C type, found {base or 'end of input'}")
        self.used_bases.add(base)
        self.position += 1
        while self._accept("*"):
            while self._peek() in _QUALIFIERS:
                self.position += 1

    def _storage(self) -> None:
        if self._peek() in _STORAGE: self.position += 1

    def _identifier(self, *, file_scope: bool = False) -> str:
        token = self._peek()
        reserved = _C_KEYWORDS | _TARGET_RESERVED_NAMES | _QUALIFIERS | _STORAGE
        if file_scope:
            reserved |= _C11_EXTERNAL_IDENTIFIERS
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token) or token.startswith("_") or token in reserved:
            raise _ParseError(f"expected identifier, found {token or 'end of input'}")
        self.position += 1
        return token

    def _declaration_start(self) -> bool:
        index = self.position
        if self.tokens[index:index+1] and self.tokens[index] in _STORAGE: index += 1
        while index < len(self.tokens) and self.tokens[index] in _QUALIFIERS: index += 1
        return (
            index < len(self.tokens)
            and self.tokens[index] in _BASE_TYPES | self.record_types
            and self.tokens[index] != "void"
        )

    def _peek(self, offset: int = 0) -> str:
        index = self.position + offset
        return self.tokens[index] if index < len(self.tokens) else ""

    def _accept(self, token: str) -> bool:
        if self._peek() == token:
            self.position += 1
            return True
        return False

    def _expect(self, token: str) -> None:
        if not self._accept(token):
            raise _ParseError(f"expected {token}, found {self._peek() or 'end of input'}")


def validate_c_text(text: str) -> CTextConformanceResult:
    if text and not text.endswith("\n"):
        return CTextConformanceResult(False, "missing final newline", 0)
    position = 0
    tokens: list[str] = []
    while position < len(text):
        match = _TOKEN.match(text, position)
        if not match:
            return CTextConformanceResult(False, f"unexpected character at byte {len(text[:position].encode('utf-8'))}", len(tokens))
        position = match.end()
        if match.lastgroup != "space":
            tokens.append(match.group(0))
    try:
        _Parser(tuple(tokens)).parse()
    except _ParseError as exc:
        return CTextConformanceResult(False, str(exc), len(tokens))
    return CTextConformanceResult(True, "accepted", len(tokens))
