from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable

@dataclass(frozen=True, slots=True)
class SourcePosition:
    line: int
    column: int
    offset: int
    def to_dict(self)->dict[str,int]: return {"line":self.line,"column":self.column,"offset":self.offset}

@dataclass(frozen=True, slots=True)
class SourceSpan:
    document_id: str
    start: SourcePosition
    end: SourcePosition
    def to_dict(self)->dict[str,object]: return {"document_id":self.document_id,"start":self.start.to_dict(),"end":self.end.to_dict()}

@dataclass(frozen=True, slots=True)
class TokenRecord:
    kind: str
    text: str
    span: SourceSpan
    def to_dict(self)->dict[str,object]: return {"kind":self.kind,"text":self.text,"span":self.span.to_dict()}

@dataclass(frozen=True, slots=True)
class SourceDocument:
    document_id: str
    logical_name: str
    text: str
    utf8_sha256: str
    line_starts: tuple[int,...]
    newline_sequences: tuple[str,...]
    tokens: tuple[TokenRecord,...]

    @classmethod
    def create(cls, logical_name:str, text:str, tokens:Iterable[TokenRecord]=())->"SourceDocument":
        raw=text.encode("utf-8")
        document_id="src-"+sha256((logical_name+"\0").encode("utf-8")+raw).hexdigest()[:20]
        starts=[0]; newlines=[]; i=0
        while i < len(text):
            if text.startswith("\r\n",i): newlines.append("\r\n"); i+=2; starts.append(i)
            elif text[i] in "\r\n": newlines.append(text[i]); i+=1; starts.append(i)
            else: i+=1
        return cls(document_id,logical_name,text,sha256(raw).hexdigest(),tuple(starts),tuple(newlines),tuple(tokens))

    def offset(self,line:int,column:int)->int:
        if line < 1 or line > len(self.line_starts): raise ValueError("line outside source")
        line_text = self._line_segment(line)
        # ``tokenize`` can report one virtual end column after a terminal bare
        # CR.  Preserve that display column while clamping its concrete source
        # offset to the document boundary.
        if column < 0 or column > len(line_text)+1: raise ValueError("column outside source line")
        return min(self.line_starts[line-1]+column,len(self.text))

    def _line_segment(self, line: int) -> str:
        start = self.line_starts[line-1]
        end = self.line_starts[line] if line < len(self.line_starts) else len(self.text)
        return self.text[start:end]

    def _line_text(self, line: int) -> str:
        value = self._line_segment(line)
        if value.endswith("\r\n"):
            return value[:-2]
        if value.endswith(("\r", "\n")):
            return value[:-1]
        return value

    def span(self,start_line:int,start_col:int,end_line:int,end_col:int)->SourceSpan:
        return SourceSpan(self.document_id,SourcePosition(start_line,start_col,self.offset(start_line,start_col)),SourcePosition(end_line,end_col,self.offset(end_line,end_col)))

    def span_from_utf8_columns(self,start_line:int,start_col:int,end_line:int,end_col:int)->SourceSpan:
        """Convert CPython AST UTF-8 byte columns into source character columns."""
        def character_column(line: int, byte_column: int) -> int:
            if byte_column < 0:
                raise ValueError("negative UTF-8 column")
            raw = self._line_text(line).encode("utf-8")
            if byte_column > len(raw):
                raise ValueError("UTF-8 column outside source line")
            try:
                return len(raw[:byte_column].decode("utf-8"))
            except UnicodeDecodeError as exc:
                raise ValueError("UTF-8 column splits a source character") from exc
        return self.span(
            start_line,
            character_column(start_line,start_col),
            end_line,
            character_column(end_line,end_col),
        )

    def to_dict(self)->dict[str,object]:
        return {"document_id":self.document_id,"logical_name":self.logical_name,"text":self.text,"utf8_sha256":self.utf8_sha256,"line_starts":list(self.line_starts),"newline_sequences":list(self.newline_sequences),"tokens":[t.to_dict() for t in self.tokens]}
