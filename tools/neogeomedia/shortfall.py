from __future__ import annotations

from typing import Final

SECONDS_PER_MINUTE: Final = 60
REFUSED: Final = "nothing here will shorten the film for you."


def shortfall(*, seconds: float, rung: str, cheapest: bool) -> str:
    if seconds < 0.0:
        msg = f"a reach cannot be negative, got {seconds:g} s"
        raise ValueError(msg)
    other = "" if cheapest else " or a cheaper --quality"
    held = int(seconds)
    if held < 1:
        cheaper = "" if cheapest else " Try a cheaper --quality."
        return f"at {rung} not even one second of this film fits.{cheaper} {REFUSED.capitalize()}"
    minutes, rest = divmod(held, SECONDS_PER_MINUTE)
    return (
        f"at {rung} the cartridge holds {minutes}m{rest:02d}s of this film. "
        f"Re-run with --duration {held}{other}; {REFUSED}"
    )
