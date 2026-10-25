"""Focused unittest coverage for the process-local PDF source cache."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import season_official_career_context_v1 as career
from scripts import season_release_registry_v1 as registry


def tiny_pdf():
    content=b"BT /F1 12 Tf 20 100 Td (Source witness) Tj ET"
    objects=[b"<< /Type /Catalog /Pages 2 0 R >>",b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",b"<< /Length "+str(len(content)).encode()+b" >>\nstream\n"+content+b"\nendstream"]
    data=b"%PDF-1.4\n";offsets=[0]
    for i,obj in enumerate(objects,1):
        offsets.append(len(data));data+=str(i).encode()+b" 0 obj\n"+obj+b"\nendobj\n"
    xref=len(data);data+=b"xref\n0 6\n0000000000 65535 f \n"+b"".join((f"{x:010d} 00000 n \n").encode() for x in offsets[1:]);data+=b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"+str(xref).encode()+b"\n%%EOF\n";return data


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class PdfTextCacheTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("pdftotext"):
            self.skipTest("pdftotext unavailable")
        self.pdf_bytes = tiny_pdf()
        self.temp = tempfile.TemporaryDirectory(prefix="pm99-pdf-cache-test-")
        self.root = Path(self.temp.name)
        seed=self.root/"extractor-seed.pdf";seed.write_bytes(self.pdf_bytes)
        self.text_bytes = subprocess.run(["pdftotext","-raw",str(seed),"-"],capture_output=True,check=True).stdout
        self.registry_root = patch.object(registry, "ROOT", self.root)
        self.registry_root.start()
        self.pdf = self.root / "witness.pdf"
        self.text = self.root / "witness.txt"
        self.pdf.write_bytes(self.pdf_bytes)
        self.text.write_bytes(self.text_bytes)
        self.source = {"document_type": "application/pdf", "path": self.pdf.name,
                       "sha256": digest(self.pdf_bytes), "text_extraction": {
                           "path": self.text.name, "sha256": digest(self.text_bytes), "extractor_mode": "-raw"}}
        career._clear_pdf_text_cache()

    def tearDown(self):
        career._clear_pdf_text_cache()
        self.registry_root.stop()
        self.temp.cleanup()

    def test_real_cold_then_warm_rehashes_pdf_and_text(self):
        calls, reads = [], []
        actual_run, actual_read = subprocess.run, career._read_binding
        def counted_run(*args, **kwargs):
            calls.append(args[0]); return actual_run(*args, **kwargs)
        def counted_read(binding):
            reads.append(binding["path"]); return actual_read(binding)
        with patch.object(career.subprocess, "run", counted_run), patch.object(career, "_read_binding", counted_read):
            expected = self.text_bytes.decode("utf-8")
            self.assertEqual(career.source_text(self.source), expected)
            self.assertEqual(career.source_text(self.source), expected)
        self.assertEqual(len(calls), 1)
        self.assertEqual(reads, [self.pdf.name, self.text.name, self.pdf.name, self.text.name])

    def test_body_and_text_tampering_fail_before_warm_cache_lookup(self):
        calls = []
        actual_run = subprocess.run
        def counted_run(*args, **kwargs):
            calls.append(args[0]); return actual_run(*args, **kwargs)
        with patch.object(career.subprocess, "run", counted_run):
            career.source_text(self.source)
            career.source_text(self.source)
            self.assertEqual(len(calls), 1)
            for target in (self.pdf, self.text):
                target.write_bytes(target.read_bytes() + b"tamper")
                before = len(calls)
                with self.assertRaisesRegex(ValueError, "digest differs"):
                    career.source_text(self.source)
                self.assertEqual(len(calls), before)
                if target == self.pdf:
                    target.write_bytes(self.pdf_bytes)
                else:
                    target.write_bytes(self.text_bytes)

    def test_identical_byte_symlinks_rejected_before_warm_cache(self):
        calls = []
        actual_run = subprocess.run
        def counted_run(*args, **kwargs):
            calls.append(args[0]); return actual_run(*args, **kwargs)
        with patch.object(career.subprocess, "run", counted_run):
            career.source_text(self.source)
            career.source_text(self.source)
            self.assertEqual(len(calls), 1)
            for target, suffix in ((self.pdf, "pdf"), (self.text, "text")):
                replacement = self.root / f"{suffix}-target.bin"
                replacement.write_bytes(target.read_bytes())
                target.unlink()
                target.symlink_to(replacement)
                before = len(calls)
                with self.assertRaisesRegex(ValueError, "regular workspace file"):
                    career.source_text(self.source)
                self.assertEqual(len(calls), before)
                target.unlink()
                target.write_bytes(self.pdf_bytes if suffix == "pdf" else self.text_bytes)

    def test_executable_mode_helper_locale_and_text_hash_invalidate(self):
        exe1, exe2 = self.root / "pdftotext-1", self.root / "pdftotext-2"
        exe1.write_bytes(b"extractor one"); exe2.write_bytes(b"extractor two")
        current_exe = [exe1]
        calls, outputs = [], [self.text_bytes]
        def exe_binding():
            return str(current_exe[0]), digest(current_exe[0].read_bytes())
        def mock_run(argv, **kwargs):
            calls.append(tuple(argv)); return SimpleNamespace(stdout=outputs[0])
        with patch.object(career, "_pdf_executable_binding", exe_binding), \
             patch.object(career, "_helper_code_fingerprint", lambda: "helper-A"), \
             patch.object(career, "_locale_fingerprint", lambda: ("locale-A",)), \
             patch.object(career.subprocess, "run", mock_run):
            career.source_text(self.source); career.source_text(self.source)
            self.assertEqual(len(calls), 1)
            current_exe[0] = exe2; career.source_text(self.source)
            self.assertEqual(len(calls), 2)
            self.source["text_extraction"]["extractor_mode"] = "-layout"
            career.source_text(self.source)
            self.assertEqual(len(calls), 3)
            with patch.object(career, "_helper_code_fingerprint", lambda: "helper-B"):
                career.source_text(self.source)
            self.assertEqual(len(calls), 4)
            with patch.object(career, "_locale_fingerprint", lambda: ("locale-B",)):
                career.source_text(self.source)
            self.assertEqual(len(calls), 5)
            changed = self.text_bytes + b"\nextra"
            self.text.write_bytes(changed)
            self.source["text_extraction"]["sha256"] = digest(changed)
            outputs[0] = changed
            self.assertEqual(career.source_text(self.source), changed.decode("utf-8"))
            self.assertEqual(len(calls), 6)

    def test_mismatch_is_not_cached_and_later_success_retries(self):
        exe = self.root / "pdftotext-mock"; exe.write_bytes(b"mock extractor")
        outputs, calls = [b"wrong text"], []
        def mock_run(argv, **kwargs):
            calls.append(tuple(argv)); return SimpleNamespace(stdout=outputs[0])
        with patch.object(career, "_pdf_executable_binding", lambda: (str(exe), digest(exe.read_bytes()))), \
             patch.object(career.subprocess, "run", mock_run):
            with self.assertRaisesRegex(ValueError, "not reproducible"):
                career.source_text(self.source)
            self.assertEqual(len(career._PDF_TEXT_CACHE), 0)
            outputs[0] = self.text_bytes
            self.assertEqual(career.source_text(self.source), self.text_bytes.decode("utf-8"))
            self.assertEqual(career.source_text(self.source), self.text_bytes.decode("utf-8"))
            self.assertEqual(len(calls), 2)

    def test_cache_has_small_fixed_bound(self):
        exe = self.root / "pdftotext-mock"; exe.write_bytes(b"mock extractor")
        outputs = [self.text_bytes]
        def mock_run(argv, **kwargs):
            return SimpleNamespace(stdout=outputs[0])
        with patch.object(career, "_pdf_executable_binding", lambda: (str(exe), digest(exe.read_bytes()))), \
             patch.object(career.subprocess, "run", mock_run):
            for i in range(career._PDF_TEXT_CACHE_MAX + 4):
                value = self.text_bytes + f"\n{i}".encode()
                self.text.write_bytes(value)
                self.source["text_extraction"]["sha256"] = digest(value)
                outputs[0] = value
                self.assertEqual(career.source_text(self.source), value.decode("utf-8"))
        self.assertEqual(len(career._PDF_TEXT_CACHE), career._PDF_TEXT_CACHE_MAX)


if __name__ == "__main__":
    unittest.main()
