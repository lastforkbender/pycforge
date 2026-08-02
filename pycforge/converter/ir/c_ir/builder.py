from __future__ import annotations
from dataclasses import dataclass, field
from .model import CExternalDeclaration,CInclude,CModuleManifestEntry,CProvenance,CTranslationUnit,LEGACY_SCHEMA_VERSION

@dataclass(slots=True)
class CTranslationUnitBuilder:
    target_contract: str
    node_id: str = "c-tu-0001"
    provenance: CProvenance = CProvenance("synthetic")
    schema_version: str = LEGACY_SCHEMA_VERSION
    module_manifest: tuple[CModuleManifestEntry,...] = ()
    module_order: tuple[str,...] = ()
    module_dependencies: tuple[tuple[str,str],...] = ()
    _includes: list[CInclude] = field(default_factory=list)
    _declarations: list[CExternalDeclaration] = field(default_factory=list)
    _sealed: bool = False
    def add_include(self, include:CInclude)->None:
        self._assert_open(); self._includes.append(include)
    def add_declaration(self, declaration:CExternalDeclaration)->None:
        self._assert_open(); self._declarations.append(declaration)
    def build(self)->CTranslationUnit:
        self._assert_open(); self._sealed=True
        includes=tuple(sorted(self._includes,key=lambda x:(not x.system,x.header,x.node_id)))
        return CTranslationUnit(self.schema_version,self.node_id,self.target_contract,includes,tuple(self._declarations),self.provenance,self.module_manifest,self.module_order,self.module_dependencies)
    def _assert_open(self)->None:
        if self._sealed: raise RuntimeError("C translation-unit builder is sealed")
