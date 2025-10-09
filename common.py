#############################################################################
#
# Copyright (C) 2018 Fabian Schweinfurth
# Contact: autoshift <at> derfabbi.de
#
# This file is part of autoshift
#
# autoshift is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# autoshift is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with autoshift.  If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################
import logging
from logging import CRITICAL, DEBUG, ERROR, INFO, NOTSET, WARNING
from os import path
import os
import sys
from datetime import datetime

try:
    import rich  # noqa: F401
    from rich.console import Console
    from rich.logging import RichHandler  # noqa: F401
    from rich.markup import escape
except ImportError as exc:  # pragma: no cover - hard requirement message
    sys.stderr.write(
        "Missing optional dependency 'rich'.\n"
        "Install the project requirements with: pip install -r requirements.txt\n"
    )
    raise SystemExit(1) from exc

FILEPATH = path.realpath(__file__)
DIRNAME = path.dirname(FILEPATH)


def dim_text(message: str) -> str:
    """Return Rich markup that styles the provided message in light grey."""
    return f"[#767676]{escape(message)}[/]"


class LegacyRichHandler(logging.Handler):
    """Reproduce the prior ANSI-styled output using Rich for rendering."""

    TIME_STYLE = "bold bright_cyan"
    BRACKET_STYLE = "bold bright_cyan"
    MODULE_STYLE = "bold bright_cyan"
    LEVEL_STYLES = {
        NOTSET: "bold bright_cyan",
        DEBUG: "bold yellow",
        INFO: "bold blue",
        WARNING: "bold magenta",
        ERROR: "bold red",
        CRITICAL: "bold red",
    }

    def __init__(self, console: Console, datefmt: str = "%Y-%m-%d %H:%M:%S"):
        super().__init__()
        self.console = console
        self.datefmt = datefmt

    def format_message(self, record: logging.LogRecord) -> str:
        base_message = record.getMessage()
        if record.exc_info and not record.exc_text:
            record.exc_text = self.formatException(record.exc_info)
        if record.exc_text:
            base_message = f"{base_message}\n{record.exc_text}"

        if getattr(record, "rich_markup", False):
            return base_message
        return escape(base_message)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format_message(record)
            asctime = datetime.fromtimestamp(record.created).strftime(self.datefmt)
            time_markup = f"[{self.TIME_STYLE}]{asctime}[/]"
            level_style = self.LEVEL_STYLES.get(record.levelno, "bold white")
            bracket_markup = (
                f"[{self.BRACKET_STYLE}][[/]"
                f"[{level_style}]{record.levelname}[/]"
                f"[{self.BRACKET_STYLE}]][/]"
            )
            spaces = " " * max(0, 8 - len(record.levelname))
            module_markup = ""
            if record.levelno == DEBUG:
                module_name = escape(record.module or "")
                module_markup = (
                    f"[{self.MODULE_STYLE}]{module_name}:{record.lineno} - [/]"
                )
            output = (
                f"{time_markup} {bracket_markup} {spaces}{module_markup}{message}"
            )
            self.console.print(output, markup=True, highlight=False)
        except Exception:
            self.handleError(record)


def initLogger():
    console = Console(color_system="standard", soft_wrap=True)
    handler = LegacyRichHandler(console=console)

    logger = logging.getLogger("autoshift")
    logger.handlers = []
    logger.addHandler(handler)
    logger.setLevel(INFO)
    logger.propagate = False
    return logger


_L = initLogger()
