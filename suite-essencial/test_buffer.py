from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stdout
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from MIR import BufferError, compile_mir_source
from MIR.functions.reqsts import ReqstsError, reqsts


TARGET = '''\
@block config:
    format section ".section"
    section text ""
    format section_end ":"
    entry text "_start"
    comment ";"
    format label_end ":"
    default text
    word_size 8
    address_size 64
    byte_order "little"
    case_sensitive true
    symbol_prefix "_"
    local_prefix "."
    undefined_symbols "error"
    duplicate_symbols "error"
    strict true
    allow_empty_sections false
@end

@block linker:
    extension ".asm"
    search_path ""
@end

@rule mov:
. IDENT
'''


MIR = '''\
::RIF_BUFFER SET 1
::RIF_BUFFER CLEAN
::RIF_REQSTS "github.com/GrandKenzy/RIFIMG/images/img.bin/main"
::RIF_BUFFER EXTRACT 0 1
mov
'''


class _Response:
    def __init__(self, data: bytes, url: str) -> None:
        self._data = data
        self._url = url
        self.headers = Message()
        self.headers["Content-Type"] = "application/octet-stream"
        self.headers["Content-Length"] = str(len(data))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._data)
        data, self._data = self._data[:size], self._data[size:]
        return data


class _Opener:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.request = None

    def open(self, request, timeout: float):
        self.request = request
        self.timeout = timeout
        return self.response


class BufferTests(unittest.TestCase):
    def test_buffer_executes_reqsts_and_exposes_half_open_extraction(self) -> None:
        response = _Response(
            b"\xde\xad",
            "https://raw.githubusercontent.com/GrandKenzy/RIFIMG/main/images/img.bin",
        )
        opener = _Opener(response)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(TARGET, encoding="utf-8")
            with patch("MIR.functions.reqsts.build_opener", return_value=opener):
                result = compile_mir_source(target, MIR)

        self.assertIsNotNone(result.buffer)
        assert result.buffer is not None
        self.assertEqual(result.buffer.capacity_bytes, 1024)
        self.assertEqual(result.buffer.data, b"\xde\xad")
        self.assertEqual(result.buffer.extractions, (b"\xde",))
        self.assertEqual(
            opener.request.full_url,
            "https://raw.githubusercontent.com/GrandKenzy/RIFIMG/main/images/img.bin",
        )

    def test_buffer_capacity_is_declared_once_and_extract_is_bounded(self) -> None:
        base = MIR.replace("::RIF_BUFFER CLEAN\n", "::RIF_BUFFER SET 1\n")
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(TARGET, encoding="utf-8")
            with self.assertRaisesRegex(BufferError, "SET solo"):
                compile_mir_source(target, base)

        invalid = MIR.replace("EXTRACT 0 1", "EXTRACT 1 3")
        response = _Response(
            b"\xde\xad",
            "https://raw.githubusercontent.com/GrandKenzy/RIFIMG/main/images/img.bin",
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(TARGET, encoding="utf-8")
            with patch("MIR.functions.reqsts.build_opener", return_value=_Opener(response)):
                with self.assertRaisesRegex(BufferError, "fuera del rango"):
                    compile_mir_source(target, invalid)

    def test_buffer_reqsts_errors_are_propagated_as_buffer_errors(self) -> None:
        invalid = MIR.replace(
            "github.com/GrandKenzy/RIFIMG/images/img.bin/main",
            "github.com/GrandKenzy/RIFIMG/images/img.txt/main",
        )
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "main.rif"
            target.write_text(TARGET, encoding="utf-8")
            output = io.StringIO()
            with redirect_stdout(output):
                with self.assertRaisesRegex(BufferError, r"\.bin"):
                    compile_mir_source(target, invalid)
            self.assertIn("Stack rif-reqsts", output.getvalue())
            self.assertIn("reqsts: reqsts solo permite archivos .bin.", output.getvalue())

    def test_reqsts_still_rejects_missing_branch_before_network(self) -> None:
        with self.assertRaisesRegex(ReqstsError, "branch"):
            reqsts("github.com/GrandKenzy/RIFIMG/images/img.bin")


if __name__ == "__main__":
    unittest.main()
