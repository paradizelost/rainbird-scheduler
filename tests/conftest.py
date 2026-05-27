"""Test bootstrap.

The scheduler unit tests exercise only the pure-Python modules (`const`,
`scheduler`) — they have no Home Assistant dependency. But importing them via
`custom_components.rainbird_scheduler.<module>` would normally execute the
package's `__init__.py`, which imports `homeassistant` and would force the full
HA stack into the test environment.

To keep the tests fast and HA-free, pre-register the package namespaces in
`sys.modules` as lightweight package stubs (with `__path__` set) *before* any
test imports them. Python then loads the requested submodules straight from
those paths and never runs the real `__init__.py`. `scheduler.py`'s
`from .const import ...` still resolves, because `const` loads as a submodule of
the same stubbed package.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_ROOT = Path(__file__).parent.parent


def _stub_package(name: str, path: Path) -> None:
    if name in sys.modules:
        return
    mod = types.ModuleType(name)
    mod.__path__ = [str(path)]
    sys.modules[name] = mod


_stub_package("custom_components", _ROOT / "custom_components")
_stub_package(
    "custom_components.rainbird_scheduler",
    _ROOT / "custom_components" / "rainbird_scheduler",
)
