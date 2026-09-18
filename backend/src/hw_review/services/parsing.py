"""Format-neutral parser registration and dispatch."""

from __future__ import annotations

from collections.abc import Iterable

from hw_review.domain.models import ReportDocument, StagedFile
from hw_review.domain.ports import DocumentParser


class ParserRegistryError(LookupError):
    """Stable parser-registry configuration or lookup failure."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ParserRegistry:
    """Dispatch parsers solely by their declared normalized format."""

    def __init__(
        self,
        parsers: Iterable[DocumentParser[StagedFile, ReportDocument]] = (),
    ) -> None:
        self._parsers: dict[str, DocumentParser[StagedFile, ReportDocument]] = {}
        for parser in parsers:
            self.register(parser)

    def register(
        self, parser: DocumentParser[StagedFile, ReportDocument]
    ) -> None:
        declared = getattr(parser, "format", None)
        if not isinstance(declared, str) or not declared.strip():
            raise ParserRegistryError(
                "INVALID_PARSER_FORMAT", "parser must declare a non-empty format"
            )
        normalized = declared.strip().upper()
        if normalized in self._parsers:
            raise ParserRegistryError(
                "DUPLICATE_PARSER", f"parser already registered for {normalized}"
            )
        self._parsers[normalized] = parser

    def for_format(
        self, format: str
    ) -> DocumentParser[StagedFile, ReportDocument]:
        normalized = format.strip().upper()
        try:
            return self._parsers[normalized]
        except KeyError as error:
            raise ParserRegistryError(
                "PARSER_NOT_FOUND", f"no parser registered for {normalized}"
            ) from error

