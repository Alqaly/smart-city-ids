import kopf
import logging

"""Compatibility shim.

This project originally used a file named `operator.py`, but that shadows Python's
stdlib `operator` module and can break imports (e.g. `enum`, `collections`).

We keep this file as a tiny shim that:
1) re-exports the built-in operator functions via `_operator`, so stdlib imports work.
2) delegates the actual Kopf operator entrypoint to `threatresponse_operator.py`.
"""

from _operator import *  # noqa: F403


def main() -> None:
    from threatresponse_operator import main as _main

    _main()


if __name__ == "__main__":
    main()
    # Validate severity threshold
