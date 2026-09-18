"""Normalized report parser adapters with lazy Word-worker imports."""

from .base import DocumentLookupError, ParserError
from .xls import XlsParseError, XlsParser
from .xlsx import XlsxParseError, XlsxParser

__all__ = [
    "DocParseError",
    "DocParser",
    "DocumentLookupError",
    "ParserError",
    "PdfParseError",
    "PdfParser",
    "XlsParseError",
    "XlsParser",
    "XlsxParseError",
    "XlsxParser",
]


def __getattr__(name: str):
    if name in {"DocParseError", "DocParser"}:
        from .doc import DocParseError, DocParser

        return {"DocParseError": DocParseError, "DocParser": DocParser}[name]
    if name in {"PdfParseError", "PdfParser"}:
        from .pdf import PdfParseError, PdfParser

        return {"PdfParseError": PdfParseError, "PdfParser": PdfParser}[name]
    raise AttributeError(name)
