# Phase 1 Facade Contract

`PythonToCConverter.convert()` accepts one immutable `ConversionRequest` plus separate observation and cancellation controls. It returns one immutable `ConversionResult`. Internal exceptions become `PYC9001` diagnostics. Only validated completed artifacts advance the pipeline. Phase 1 success proves the control plane only and intentionally returns `generated_c = None`.
