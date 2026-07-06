"""Command-line entry point: `retirement-sim <config.yaml> [options]`."""

from __future__ import annotations

import argparse
import sys

from .config import ConfigError, load_config
from .report import format_summary, save_charts
from .simulate import run_simulation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="retirement-sim",
        description="Monte Carlo simulator for retirement account goals.",
    )
    parser.add_argument("config", help="path to a YAML plan config")
    parser.add_argument("--sims", type=int, default=None, help="override simulation.n_sims")
    parser.add_argument("--seed", type=int, default=None, help="override simulation.seed")
    parser.add_argument("--output-dir", default=None, help="override output.dir for charts")
    parser.add_argument("--no-charts", action="store_true", help="skip chart generation")
    parser.add_argument("--show", action="store_true",
                        help="open the charts in interactive windows (in addition to saving PNGs)")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    results = run_simulation(config, n_sims=args.sims, seed=args.seed)
    print(format_summary(results))

    if config.output.charts and not args.no_charts:
        show = args.show or config.output.show
        paths = save_charts(results, args.output_dir or config.output.dir, show=show)
        print("Charts written:")
        for path in paths:
            print(f"  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
