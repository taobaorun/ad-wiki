#!/usr/bin/env python3
"""Deprecated compatibility entrypoint; staged runs apply directly in v1.2."""

from ad_wiki.cli import approve_main


if __name__ == "__main__":
    raise SystemExit(approve_main())
