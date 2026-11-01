"""Bounded raw-binary downloads from GitHub."""

from __future__ import annotations

import socket
import sys
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from gram.utilities import Diagnostics
from rif_core.limits import resolve_limits


MAX_REQSTS_BYTES = 16 << 20
REQSTS_TIMEOUT_SECONDS = 15
_SOURCE_HOST = "github.com"
_RAW_HOST = "raw.githubusercontent.com"
_USER_AGENT = "RIF-reqsts/1"
_GITHUB_HOSTS = frozenset({_SOURCE_HOST, _RAW_HOST})
_DIAGNOSTICS = Diagnostics(
    "rif-reqsts",
    "REQSTS",
    "Diagnósticos de adquisición binaria externa",
)


class ReqstsError(ValueError):
    """A remote GitHub binary cannot be safely fetched."""


def _report_error(message: str) -> None:
    """Publish one reqsts failure through Gram's structured console output."""

    # This operation runs in Python's external buffer phase; DiagnosticsLite is
    # reserved for the generated C lexer/parser and cannot report this failure.
    _DIAGNOSTICS.stack.clean()
    _DIAGNOSTICS.error(f"reqsts: {message}")
    rendered = _DIAGNOSTICS.stack.stringify(ansi=False)
    try:
        print(rendered)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
        safe = rendered.encode(encoding, errors="replace").decode(encoding)
        print(safe)


class _GitHubRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, file, code, message, headers, newurl):
        target = urlsplit(newurl)
        if target.scheme != "https" or target.hostname not in _GITHUB_HOSTS:
            raise ReqstsError("reqsts rechazó una redirección fuera de GitHub.")
        return super().redirect_request(request, file, code, message, headers, newurl)


def _segments(source: str) -> tuple[str, ...]:
    if not isinstance(source, str) or not source.strip():
        raise ReqstsError("reqsts requiere una ruta GitHub no vacía.")
    if any(character.isspace() for character in source):
        raise ReqstsError("reqsts no acepta espacios en la ruta GitHub.")

    parsed = urlsplit(source if "://" in source else f"https://{source}")
    if parsed.scheme != "https" or parsed.hostname != _SOURCE_HOST:
        raise ReqstsError("reqsts solo acepta rutas HTTPS de github.com.")
    if parsed.port is not None or parsed.username or parsed.password:
        raise ReqstsError("reqsts no acepta puertos ni credenciales.")
    if parsed.query or parsed.fragment:
        raise ReqstsError("reqsts no acepta query strings ni fragmentos.")

    raw_segments = parsed.path.strip("/").split("/")
    if len(raw_segments) < 4 or any(not segment for segment in raw_segments):
        raise ReqstsError(
            "reqsts requiere github.com/owner/repo/ruta.bin/branch."
        )
    if unquote(raw_segments[-1]).lower().endswith(".bin"):
        raise ReqstsError("reqsts requiere el branch al final de la ruta.")

    segments = tuple(unquote(segment) for segment in raw_segments)
    if any(
        segment in {".", ".."}
        or "/" in segment
        or "\\" in segment
        or "\x00" in segment
        for segment in segments
    ):
        raise ReqstsError("reqsts contiene una ruta GitHub insegura.")
    if not segments[0] or not segments[1]:
        raise ReqstsError("reqsts requiere owner y repositorio.")

    file_path = "/".join(segments[2:-1])
    branch = segments[-1]
    if not file_path.lower().endswith(".bin"):
        raise ReqstsError("reqsts solo permite archivos .bin.")
    if not branch:
        raise ReqstsError("reqsts requiere el branch al final de la ruta.")
    return segments


def _raw_url(segments: tuple[str, ...]) -> str:
    owner, repository = segments[:2]
    file_segments = segments[2:-1]
    branch = segments[-1]
    encoded = [quote(item, safe="-._~") for item in (owner, repository, branch)]
    encoded_path = "/".join(quote(item, safe="-._~@") for item in file_segments)
    return f"https://{_RAW_HOST}/{encoded[0]}/{encoded[1]}/{encoded[2]}/{encoded_path}"


def _read_bounded(response: BinaryIO, maximum: int) -> bytes:
    content_length = response.headers.get("Content-Length")
    if content_length is not None:
        try:
            announced = int(content_length)
        except (TypeError, ValueError) as exc:
            raise ReqstsError("GitHub devolvió un Content-Length inválido.") from exc
        if announced < 0 or announced > maximum:
            raise ReqstsError("El archivo remoto excede el límite de reqsts.")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = response.read(min(64 << 10, maximum - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > maximum:
            raise ReqstsError("El archivo remoto excede el límite de reqsts.")
        chunks.append(chunk)
    return b"".join(chunks)


def reqsts(source: str) -> bytes:
    """Download one raw ``.bin`` file from GitHub and return its bytes."""

    try:
        segments = _segments(source)
        maximum = resolve_limits().cap(MAX_REQSTS_BYTES)
        request = Request(
            _raw_url(segments),
            headers={"User-Agent": _USER_AGENT, "Accept": "application/octet-stream"},
            method="GET",
        )
        with build_opener(_GitHubRedirectHandler()).open(
            request, timeout=REQSTS_TIMEOUT_SECONDS
        ) as response:
            final = urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname not in _GITHUB_HOSTS:
                raise ReqstsError("reqsts rechazó una redirección fuera de GitHub.")
            content_type = response.headers.get_content_type()
            if content_type == "text/html":
                raise ReqstsError("GitHub devolvió HTML en lugar de un binario raw.")
            return _read_bounded(response, maximum)
    except ReqstsError as exc:
        _report_error(str(exc))
        raise
    except HTTPError as exc:
        error = ReqstsError(f"GitHub respondió HTTP {exc.code} para reqsts.")
        _report_error(str(error))
        raise error from exc
    except (URLError, TimeoutError, socket.timeout, OSError) as exc:
        error = ReqstsError(f"No se pudo descargar el archivo de GitHub: {exc}")
        _report_error(str(error))
        raise error from exc


__all__ = [
    "MAX_REQSTS_BYTES",
    "REQSTS_TIMEOUT_SECONDS",
    "ReqstsError",
    "reqsts",
]
