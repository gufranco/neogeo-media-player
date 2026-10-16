from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from neogeomedia import quality, tiercache


@dataclass(frozen=True, slots=True)
class Reading:
    tier: quality.Tier
    tiles: int
    capped: bool
    exhausted: bool = False

    def fits(self, budget: int) -> bool:
        return not self.capped and not self.exhausted and self.tiles <= budget


@dataclass(slots=True)
class Outcome:
    tier: quality.Tier | None
    minutes: float
    rates: dict[str, float | None] = field(default_factory=dict)
    baked: list[str] = field(default_factory=list)
    too_expensive: list[str] = field(default_factory=list)


def candidates(source_fps: float | None, vblank_fps: float | None) -> list[quality.Tier]:
    if source_fps is None or vblank_fps is None:
        return list(quality.LADDER)
    return [
        tier
        for tier in quality.LADDER
        if quality.reachable(tier, source_fps=source_fps, vblank_fps=vblank_fps)
    ]


def search(
    *,
    measure: Callable[[quality.Tier], Reading],
    minutes: float,
    budget: int,
    known: dict[str, float | None],
    source_fps: float | None = None,
    vblank_fps: float | None = None,
) -> Outcome:
    outcome = Outcome(tier=None, minutes=minutes, rates=dict(known))
    rungs = candidates(source_fps, vblank_fps)

    def fits(index: int) -> bool:
        return _fits(rungs[index], outcome, measure=measure, minutes=minutes, budget=budget)

    low, high = _bracket(len(rungs), fits)
    while low < high:
        middle = (low + high) // 2
        if fits(middle):
            high = middle
        else:
            low = middle + 1

    if low < len(rungs):
        outcome.tier = rungs[low]
    return outcome


def _bracket(count: int, fits: Callable[[int], bool]) -> tuple[int, int]:
    if count == 0:
        return 0, 0
    if fits(0):
        return 0, 0
    stride, previous = 1, 0
    while stride < count:
        if fits(stride):
            return previous + 1, stride
        previous = stride
        stride *= 2
    if previous + 1 >= count:
        return count, count
    return previous + 1, count


def _fits(
    tier: quality.Tier,
    outcome: Outcome,
    *,
    measure: Callable[[quality.Tier], Reading],
    minutes: float,
    budget: int,
) -> bool:
    if tiercache.settled(outcome.rates, tier):
        return tiercache.fits(outcome.rates, tier)

    reading = measure(tier)
    outcome.baked.append(tier.name)
    if not reading.fits(budget):
        outcome.rates[tier.name] = None
        outcome.too_expensive.append(tier.name)
        return False

    outcome.rates[tier.name] = reading.tiles / minutes
    return True
