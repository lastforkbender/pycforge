from __future__ import annotations
import ast, io, token, tokenize
from dataclasses import replace
from .source_document import SourceDocument, TokenRecord

class ParserVersionError(ValueError): pass

class Python311ParserAdapter:
    grammar_version="3.11"
    def tokenize(self,document:SourceDocument)->SourceDocument:
        records=[]
        reader=io.StringIO(document.text).readline
        for item in tokenize.generate_tokens(reader):
            if item.type==token.ENDMARKER: continue
            span=document.span(item.start[0],item.start[1],item.end[0],item.end[1])
            records.append(TokenRecord(token.tok_name[item.type],item.string,span))
        return replace(document,tokens=tuple(records))
    def parse(self,document:SourceDocument,requested_version:str)->ast.Module:
        if requested_version != self.grammar_version: raise ParserVersionError(f"unsupported grammar {requested_version}")
        return ast.parse(document.text,filename=document.logical_name,mode="exec",feature_version=(3,11),type_comments=True)
