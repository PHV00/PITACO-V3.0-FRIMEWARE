"""Regression tests for the firmware quality gate reporter (no hardware required)."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "firmware_quality_report.py"


class FirmwareQualityReportTests(unittest.TestCase):
    def run_gate(self, xml='<results version="2"><errors/></results>', cpp=0,
                 clang="", clang_exit=0):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            reports = root / "reports"
            reports.mkdir()
            if xml is not None:
                (reports / "cppcheck.xml").write_text(xml)
            (reports / "cppcheck-exit-code.txt").write_text(str(cpp))
            (reports / "clang-tidy.txt").write_text(clang)
            (reports / "clang-tidy-exit-code.txt").write_text(str(clang_exit))
            cmd = [sys.executable, str(SCRIPT), "--reports", str(reports),
                   "--workspace", str(root)]
            result = subprocess.run(cmd, capture_output=True, text=True)
            parsed = json.loads((reports / "issues.json").read_text())
            self.assertTrue((reports / "SUMMARY.md").exists())
            self.assertTrue((reports / "report.html").exists())
            return result.returncode, parsed

    def test_no_findings_pass(self):
        rc, data = self.run_gate()
        self.assertEqual(rc, 0)
        self.assertEqual(data["gate"], "PASS")

    def test_style_is_visible_and_nonblocking(self):
        xml = ('<results><errors><error id="cstyleCast" severity="style" msg="style">'
               '<location file="test/test_firmware_quality_report.py" line="1"/>'
               '</error></errors></results>')
        rc, data = self.run_gate(xml=xml, cpp=2)
        self.assertEqual(rc, 0)
        self.assertEqual(len(data["findings"]), 1)

    def test_first_party_error_blocks(self):
        xml = ('<results><errors><error id="nullPointer" severity="error" msg="bad">'
               '<location file="test/test_firmware_quality_report.py" line="1"/>'
               '</error></errors></results>')
        rc, data = self.run_gate(xml=xml, cpp=2)
        self.assertEqual(rc, 1)
        self.assertEqual(data["gate"], "FAIL")

    def test_clang_toolchain_failure_blocks(self):
        rc, data = self.run_gate(clang="error: unknown compiler argument", clang_exit=1)
        self.assertEqual(rc, 1)
        self.assertIn("Clang-Tidy", " ".join(data["failures"]))

    def test_invalid_xml_blocks(self):
        rc, _ = self.run_gate(xml="<broken")
        self.assertEqual(rc, 1)

    def test_missing_xml_blocks(self):
        rc, _ = self.run_gate(xml=None)
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
