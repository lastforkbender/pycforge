from __future__ import annotations
from pycforge.converter.frontend.stages import SourceDocumentStage,ParseStage,NormalizeStage
from pycforge.converter.modules.stage import ModuleResolutionStage
from pycforge.converter.analysis.stage import AnalysisPlanningStage
from pycforge.converter.lowering import FirstSliceLoweringStage
class Pipeline:
    def __init__(self,stages=None)->None:
        self.stages=tuple(stages or (SourceDocumentStage(),ParseStage(),NormalizeStage(),ModuleResolutionStage(),AnalysisPlanningStage(),FirstSliceLoweringStage()))
