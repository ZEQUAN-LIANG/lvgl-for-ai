from __future__ import annotations

from typing import Any

from command_session import CommandError, CommandSession


class PageError(RuntimeError):
    def __init__(self, message: str, *, code: str = "page_error") -> None:
        super().__init__(message)
        self.code = code


class PageController:
    def __init__(self, session: CommandSession) -> None:
        self._session = session

    def _exchange(self, command: str, pattern: str) -> str:
        try:
            return self._session.exchange(command, pattern)
        except CommandError as exc:
            raise PageError(str(exc), code="page_timeout") from exc

    def pages(self) -> dict[str, Any]:
        line = self._exchange("pages", r"@PAGES [^\r\n]*")
        names = line[len("@PAGES ") :].strip()
        pages = [name for name in names.split(",") if name]
        current = None
        try:
            current = self.state()
        except PageError:
            pass
        return {"pages": pages, "current": current}

    def show(self, name: str) -> str:
        if not name:
            raise PageError("page name is empty", code="page_name_empty")
        if any(char in name for char in " \t\r\n"):
            raise PageError(
                f"invalid page name: {name!r}", code="page_name_invalid"
            )
        line = self._exchange(f"page {name}", r"@(OK|ERR) PAGE [^\r\n]*")
        if line.startswith("@ERR"):
            detail = line[len("@ERR PAGE ") :].strip()
            raise PageError(
                f"firmware rejected page {name!r}: {detail}",
                code="page_unknown",
            )
        return line[len("@OK PAGE ") :].strip()

    def next(self) -> str:
        line = self._exchange("page next", r"@(OK|ERR) PAGE [^\r\n]*")
        if line.startswith("@ERR"):
            raise PageError(line, code="page_next_failed")
        return line[len("@OK PAGE ") :].strip()

    def prev(self) -> str:
        line = self._exchange("page prev", r"@(OK|ERR) PAGE [^\r\n]*")
        if line.startswith("@ERR"):
            raise PageError(line, code="page_prev_failed")
        return line[len("@OK PAGE ") :].strip()

    def state(self) -> str:
        line = self._exchange("state", r"@STATE page=[^\r\n]*")
        return line[len("@STATE page=") :].strip()

    def ping(self) -> bool:
        line = self._exchange("ping", r"@PONG")
        return line == "@PONG"
