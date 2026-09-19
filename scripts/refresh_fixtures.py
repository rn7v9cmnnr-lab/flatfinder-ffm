#!/usr/bin/env python3
"""Test-Fixtures gegen die echten APIs neu ziehen.

Nur laufen lassen, wenn ein Portal sein Format nachweislich geaendert hat -
und danach die Tests ansehen, nicht blind gruen machen. Ein Fixture-Update,
das einen echten Bruch zudeckt, ist schlimmer als ein roter Test.

    python scripts/refresh_fixtures.py
"""
import asyncio
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "src"))

from flatfinder.adapters.vonovia import VonoviaAdapter  # noqa: E402

FIXTURES = pathlib.Path(__file__).parent.parent / "tests" / "fixtures"


async def main() -> None:
    async with VonoviaAdapter() as a:
        page = await a._page(0)
    target = FIXTURES / "vonovia_list_ffm.json"
    target.write_text(json.dumps(page, indent=2, ensure_ascii=False))
    print(f"{target.name}: {len(page['results'])} Objekte")


if __name__ == "__main__":
    asyncio.run(main())
