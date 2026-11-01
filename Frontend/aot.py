"""Canonical in-memory Gram C/AOT frontend bridge.

The native FFI owns lexing and parsing and returns GIR bytes directly. RIF
semantic processing remains in Python after the GIR-to-AST boundary.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from gram import lexer
from gram.core.ast.nodes import (
    ArrayNode,
    ASTKeyword,
    ASTRef,
    Identifier,
    LiteralNumber,
    LiteralString,
    LiteralSymbol,
    RawNode,
)
from gram.ir import GirView, load_gir
from rif_contract import AOT_CACHE_FORMAT_VERSION, AOT_MODE


class _GramIrBlob(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.POINTER(ctypes.c_uint8)),
        ("size", ctypes.c_size_t),
    ]


class _GramDriverError(ctypes.Structure):
    _fields_ = [
        ("status", ctypes.c_int),
        ("line", ctypes.c_uint32),
        ("column", ctypes.c_uint32),
        ("offset", ctypes.c_uint32),
        ("message", ctypes.c_char * 192),
    ]


class AOTError(RuntimeError):
    """Raised when the native Gram frontend cannot be built or executed."""


class GIRAdapter:
    """Translate a native GIR tree to the AST shape consumed by RIF.

    The native parser owns recognition and tree structure. Terminal tokens and
    CaptureRaw tokens are materialized through Gram's GIR reader; RIF does not
    re-tokenize the source with its Python lexer.
    """

    def __init__(self, document: GirView) -> None:
        self.document = document
        if document.source_bytes is None:
            raise AOTError("El GIR debe asociarse con la fuente original.")

    def _terminal(self, node: Any) -> Any:
        expected = lexer.Token.from_code(node.value)
        if expected is None:
            raise AOTError(
                f"No se pudo asociar el terminal GIR {node.kind_name!r} "
                f"en {node.line}:{node.column}."
            )
        token = lexer.TokenType(
            expected,
            None if expected in {lexer.Token.NEWLINE, lexer.Token.EOF} else node.typed_value,
            line=max(0, node.line - 1),
            col=node.column,
        )
        if expected == lexer.Token.KEYWORD:
            return ASTKeyword(token)
        if expected == lexer.Token.IDENT:
            return Identifier(token)
        if expected == lexer.Token.STRING:
            return LiteralString(token)
        if expected in {lexer.Token.NUMBER, lexer.Token.DECIMAL, lexer.Token.BOOL}:
            return LiteralNumber(token)
        return LiteralSymbol(token)

    def _raw(self, node: Any) -> RawNode:
        start = node.src_start
        end = start + node.src_length
        if node.src_length == 0 and node.token_count:
            tokens = (
                lexer.TokenType(
                    lexer.Token.NEWLINE,
                    None,
                    line=max(0, node.line - 1),
                    col=node.column,
                ),
            )
        else:
            tokens = tuple(node.tokens)
        # Keep the same newline representation as the Python frontend's
        # read_text() path.
        raw_text = self.document.source_bytes[start:end].decode("utf-8", errors="replace")
        text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
        return RawNode(tokens, text)

    def _node(self, node: Any) -> Any:
        if node.is_raw:
            return self._raw(node)
        if node.flags & 0x01:
            return self._terminal(node)
        children = [self._node(child) for child in node.children]
        if node.flags & 0x08:
            # RIF visitors consume Gram's repeated sequences as Python lists.
            # Keep ARRAY transparent at this representation boundary.
            return children
        if node.flags & 0x02:
            if node.symbol_name == "RULE" and len(children) > 5:
                # The C emitter flattens the result of Many(INSTRUCTION),
                # while newer GIR versions wrap the flat stream in ARRAY.
                # Rebuild one list per instruction by using the top-level DOT
                # marker; instruction payloads are variable length, especially
                # for frame.
                prefix = children[:5]
                sequence = children[5]
                flat = list(sequence) if isinstance(sequence, (list, tuple, ArrayNode)) else children[5:]
                instructions: list[list[Any]] = []
                current: list[Any] = []
                for item in flat:
                    token = getattr(item, "token", None)
                    if token is not None and token.token == lexer.Token.DOT and current:
                        instructions.append(current)
                        current = []
                    current.append(item)
                if current:
                    instructions.append(current)
                if not instructions:
                    raise AOTError("La secuencia de instrucciones GIR está vacía.")
                return ASTRef(node.symbol_name, prefix + [instructions])
            if node.symbol_name == "ASMVARIANT" and len(children) >= 8:
                # Python Gram keeps the repeated variant directives in one
                # list; GIR may expose them as direct children or an ARRAY.
                prefix = children[:5]
                sequence = children[5]
                if isinstance(sequence, (list, tuple, ArrayNode)):
                    directives = list(sequence.items) if isinstance(sequence, ArrayNode) else list(sequence)
                    suffix = children[6:]
                else:
                    directives = []
                    index = 5
                    while index < len(children) - 3:
                        directives.append(children[index])
                        index += 1
                    suffix = children[-3:]
                return ASTRef(node.symbol_name, prefix + [directives] + suffix)
            return ASTRef(node.symbol_name, children)
        raise AOTError(f"Tipo de nodo GIR no soportado: {node.flags:#x}.")

    def ast(self) -> list[Any]:
        root = self.document.root
        if not root.flags & 0x08:
            raise AOTError("La raíz GIR de RIF no es un ARRAY.")
        result = []
        for entrypoint in root.children:
            children = entrypoint.children
            if len(children) != 1 or not (entrypoint.flags & 0x02):
                raise AOTError("La raíz GIR contiene un ENTRYPOINT inválido.")
            result.append(self._node(children[0]))
        return result


@dataclass
class AOTParser:
    output_dir: Path
    library: Path
    session: Any
    _ffi: Any = field(default=None, init=False, repr=False)

    @property
    def executable(self) -> Path:
        """Compatibility name for the cached native AOT library path."""

        return self.library

    @staticmethod
    def default_cache_dir() -> Path:
        """Return RIF's persistent cache for the generated AOT compiler."""

        return Path(__file__).resolve().parents[1] / ".rif-cache" / "aot"

    @staticmethod
    def _native_sources_digest(native: Path) -> str:
        digest = hashlib.sha256()
        files = sorted(
            path
            for root in (native / "include", native / "src")
            for path in root.rglob("*")
            if path.is_file() and path.suffix in {".c", ".h"}
        )
        for path in files:
            digest.update(path.relative_to(native).as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _input_sources_digest(gram_root: Path) -> str:
        """Hash sources that can change the generated parser before exporting."""

        digest = hashlib.sha256()
        roots = (
            Path(__file__).resolve().parent / "syntax",
            gram_root / "gram",
            gram_root / "tools",
        )
        files = sorted(
            path
            for root in roots
            for path in root.rglob("*")
            if path.is_file() and path.suffix in {".py", ".json"}
        )
        for path in files:
            digest.update(path.as_posix().encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
        return digest.hexdigest()

    @classmethod
    def build(cls, output_dir: str | Path, session: Any) -> "AOTParser":
        output = Path(output_dir).resolve()
        output.mkdir(parents=True, exist_ok=True)
        with cls._cache_lock(output / "rif_aot_build.lock"):
            return cls._build_locked(output, session)

    @staticmethod
    @contextmanager
    def _cache_lock(lock_path: Path):
        """Serialize cache validation/export/build across RIF processes."""

        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("a+b") as handle:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"0")
                    handle.flush()
                while True:
                    try:
                        handle.seek(0)
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        time.sleep(0.05)
                try:
                    yield
                finally:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @classmethod
    def _build_locked(cls, output: Path, session: Any) -> "AOTParser":
        compiler = shutil.which("gcc") or shutil.which("clang")
        if compiler is None:
            raise AOTError("No se encontró gcc ni clang para compilar el parser AOT.")
        import gram
        from rif_contract import current_contract

        gram_root = Path(gram.__file__).resolve().parents[1]
        native = gram_root / "native" / "gram_lexer"
        cache_manifest_path = output / "rif_aot_build.json"
        library = output / (
            "rif-gram-aot.dll" if os.name == "nt" else "librif-gram-aot.so"
        )
        compiler_path = Path(compiler).resolve()
        compiler_stat = compiler_path.stat()
        contract = current_contract()
        cache_inputs = {
            "cache_format_version": AOT_CACHE_FORMAT_VERSION,
            "aot_mode": AOT_MODE,
            "contract_fingerprint": contract.fingerprint(),
            "input_sources_hash": cls._input_sources_digest(gram_root),
            "native_sources_hash": cls._native_sources_digest(native),
            "compiler": str(compiler_path),
            "compiler_mtime_ns": compiler_stat.st_mtime_ns,
            "compiler_size": compiler_stat.st_size,
        }
        if library.is_file() and cache_manifest_path.is_file():
            try:
                cache_manifest = json.loads(cache_manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cache_manifest = None
            if cache_manifest and all(
                cache_manifest.get(name) == value
                for name, value in cache_inputs.items()
            ):
                return cls(output, library, session)

        session.export_c_parser(output, emit_driver=True, emit_cli=False)
        # Older Gram exporters left the CLI translation unit in this cache.
        # It is not linked by the FFI build and must not survive as a stale
        # second entry point beside the in-memory driver.
        (output / "gram_cli.c").unlink(missing_ok=True)
        parser_manifest_path = output / "gram_parser_manifest.json"
        lexer_manifest_path = output / "gram_lexer_manifest.json"
        generated = [
            output / name
            for name in ("gram_ast.c", "gram_parser.c", "gram_ir.c", "gram_driver.c")
        ]
        generated.extend(output.glob("gram_lexer_*.c"))
        generated.extend(native.joinpath("src").glob("*.c"))
        parser_manifest = json.loads(parser_manifest_path.read_text(encoding="utf-8"))
        lexer_manifest = json.loads(lexer_manifest_path.read_text(encoding="utf-8"))
        cache_key_data = {
            **cache_inputs,
            "parser_content_hash": parser_manifest.get("content_hash"),
            "lexer_content_hash": lexer_manifest.get("content_hash"),
        }
        cache_key = hashlib.sha256(
            json.dumps(cache_key_data, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if library.is_file() and cache_manifest_path.is_file():
            try:
                cache_manifest = json.loads(cache_manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                cache_manifest = None
            if cache_manifest and cache_manifest.get("cache_key") == cache_key:
                return cls(output, library, session)
        command = [
            compiler,
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-shared",
            *([] if os.name == "nt" else ["-fPIC"]),
            "-I",
            str(native / "include"),
            "-I",
            str(native / "src"),
            "-I",
            str(output),
            *(str(path) for path in generated),
            "-o",
            str(library),
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        if completed.returncode:
            library.unlink(missing_ok=True)
            raise AOTError(completed.stderr or "Falló la compilación del parser AOT.")
        cache_manifest_path.write_text(
            json.dumps(
                {
                    "cache_key": cache_key,
                    **cache_inputs,
                    "contract": contract.as_dict(),
                    "parser_content_hash": parser_manifest.get("content_hash"),
                    "lexer_content_hash": lexer_manifest.get("content_hash"),
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
            newline="\n",
        )
        return cls(output, library, session)

    def _ffi_library(self) -> Any:
        if self._ffi is not None:
            return self._ffi
        if not self.library.is_file():
            raise AOTError(f"No se encontró la biblioteca AOT: {self.library}")
        try:
            library = ctypes.CDLL(str(self.library))
            compile_source = library.gram_compile_source_to_ir
            compile_source.argtypes = [
                ctypes.c_void_p,
                ctypes.c_size_t,
                ctypes.POINTER(_GramIrBlob),
                ctypes.POINTER(_GramDriverError),
            ]
            compile_source.restype = ctypes.c_int
            free_blob = library.gram_ir_blob_free
            free_blob.argtypes = [ctypes.POINTER(_GramIrBlob)]
            free_blob.restype = None
        except (AttributeError, OSError) as exc:
            raise AOTError(
                f"No se pudo cargar la FFI AOT desde '{self.library}': {exc}"
            ) from exc
        self._ffi = (library, compile_source, free_blob)
        return self._ffi

    @staticmethod
    def _ffi_error(error: _GramDriverError, name: str) -> str:
        raw = bytes(error.message).split(b"\0", 1)[0]
        message = raw.decode("utf-8", errors="replace") or "fallo AOT"
        location = (
            f"{name}:{error.line}:{error.column}: "
            if error.line
            else f"{name}: "
        )
        return location + message

    def parse_source(
        self,
        source: str | bytes | bytearray | memoryview,
        name: str = "<memory>",
    ) -> GirView:
        """Parse RIF through Gram's C driver and keep GIR entirely in memory."""

        if isinstance(source, str):
            source_bytes = source.encode("utf-8")
        elif isinstance(source, (bytes, bytearray, memoryview)):
            source_bytes = bytes(source)
        else:
            raise TypeError(f"La fuente AOT debe ser texto o bytes, no {type(source).__name__}.")
        buffer = ctypes.create_string_buffer(source_bytes)
        blob = _GramIrBlob()
        error = _GramDriverError()
        _, compile_source, free_blob = self._ffi_library()
        status = compile_source(
            ctypes.cast(buffer, ctypes.c_void_p),
            len(source_bytes),
            ctypes.byref(blob),
            ctypes.byref(error),
        )
        if status != 0:
            raise AOTError(self._ffi_error(error, name))
        try:
            if not blob.data or blob.size == 0:
                raise AOTError(f"{name}: Gram no produjo GIR.")
            gir = ctypes.string_at(blob.data, blob.size)
            return load_gir(gir, source_text=source_bytes, session=self.session)
        finally:
            free_blob(ctypes.byref(blob))

    def parse_file(self, source_path: str | Path) -> GirView:
        source_path = Path(source_path).expanduser().resolve()
        return self.parse_source(source_path.read_bytes(), str(source_path))


__all__ = ["AOTError", "AOTParser", "GIRAdapter"]
