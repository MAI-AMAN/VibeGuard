"""VibeGuard: human-gated software reliability automation."""

__version__ = "0.1.0"


def main() -> None:
    """Compatibility entry point."""
    from vibeguard.main import main as cli_main

    cli_main()
