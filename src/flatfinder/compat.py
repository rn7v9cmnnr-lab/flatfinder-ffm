"""Kleine Bruecke zu aelteren Python-Versionen.

Grund: macOS liefert Python 3.9 mit. Wer das Projekt auf einem frischen Mac
startet, hat genau das - und soll nicht erst Homebrew und ein neues Python
installieren muessen, nur um eine Wohnungsliste zu sehen.

`StrEnum` gibt es erst ab 3.11. Der Ersatz verhaelt sich absichtlich
identisch, inklusive `str(Status.NEW) == "new"` - ohne das
`__str__` liefert ein (str, Enum) naemlich "Status.NEW", und genau das
landet dann in der Datenbank.
"""

from __future__ import annotations

import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        def __str__(self) -> str:
            return str(self.value)

__all__ = ["StrEnum"]
