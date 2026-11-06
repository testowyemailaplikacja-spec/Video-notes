"""PyInstaller entry point for internal development executable.

No licensed speech models, FFmpeg, or other third-party runtimes bundled.
"""
from videonotes.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
