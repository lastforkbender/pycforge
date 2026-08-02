from __future__ import annotations

import hashlib
import json
import unittest

from pycforge import ConversionRequest, PythonToCConverter, __version__
from pycforge.converter.contracts.versions import CONVERTER_CONTRACT_VERSION
from pycforge.converter.core.request import ObservationOptions
from pycforge.converter.core.serialization import result_to_dict
from pycforge.ide import WORKSPACE_CONTRACT_VERSION


CHECKPOINT_SOURCE = """\
def add(a: int, /, b: int, *, scale: int) -> int:
    return (a + b) * scale

def run() -> int:
    return add(1, b=2, scale=3)
"""


class CheckpointEVersioningTests(unittest.TestCase):
    def test_phase15c_distribution_advances_without_semantic_identity_churn(self) -> None:
        self.assertEqual(__version__, "0.15.2")
        self.assertEqual(CONVERTER_CONTRACT_VERSION, "0.14.3")
        self.assertEqual(WORKSPACE_CONTRACT_VERSION, "pycforge-workspace/0.5")

        result = PythonToCConverter().convert(
            ConversionRequest.from_source(CHECKPOINT_SOURCE),
            observation=ObservationOptions("Full", True),
        )

        self.assertEqual(result.status.value, "Converted")
        self.assertEqual(
            result.output_fingerprint.value,
            "685607a0916efeeef5300966bc30e5a9c5b9ad21c3929b7b681db2c8fe050418",
        )
        self.assertEqual(
            hashlib.sha256(result.generated_c.encode("utf-8")).hexdigest(),
            "5c85b6ca4b6ff59f2c6c073df4967db17ef64a5c8d1eda926e528cc45c20eb84",
        )
        self.assertEqual(result.decision_trace["converter_version"], "0.14.3")
        serialized = json.dumps(
            result_to_dict(result),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(
            hashlib.sha256(serialized).hexdigest(),
            "2570d9846aa30134894f931739dfb867de010021f81db2fa5d801fbf397bd441",
        )


if __name__ == "__main__":
    unittest.main()
