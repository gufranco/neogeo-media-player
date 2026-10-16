from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Final

from fmvcore import fetch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from neogeomedia import clips

USER_AGENT: Final = (
    "neogeo-media-player-clips/1.0 (+https://github.com/gufranco/neogeo-media-player)"
)
DOWNLOAD: Final = fetch.downloader(USER_AGENT)


def acquire(
    clip: clips.Clip, *, download: fetch.Download = DOWNLOAD, wait: fetch.Wait = time.sleep
) -> fetch.Outcome:
    return fetch.acquire(
        clip,
        clips.path_of(clip),
        fetch_command=clips.FETCH_COMMAND,
        download=download,
        wait=wait,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fetch_clips")
    parser.add_argument("keys", nargs="*", help="fetch only these clips")
    args = parser.parse_args(argv)

    manifest = clips.load()
    unknown = sorted(set(args.keys) - {clip.key for clip in manifest})
    if unknown:
        known = ", ".join(clip.key for clip in manifest)
        print(f"not in the manifest: {', '.join(unknown)}; it holds {known}", file=sys.stderr)
        return 2
    wanted = [clip for clip in manifest if not args.keys or clip.key in args.keys]

    outcomes = [acquire(clip) for clip in wanted]
    for outcome in outcomes:
        print(f"[{outcome.action:>10}] {outcome.key}: {outcome.diagnosis}")
    failures = sum(1 for outcome in outcomes if not outcome.ok)
    print(f"\n{len(wanted) - failures} of {len(wanted)} clips are ready in {clips.directory()}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
