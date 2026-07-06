"""Allow `python -m retirement_sim <config.yaml>`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
