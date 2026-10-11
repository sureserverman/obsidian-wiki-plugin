#!/usr/bin/env python3
"""Explicit local pilot refresh/check; never granted to the answer client."""
import sys
sys.dont_write_bytecode = True
from wiki_access.cli import main

if __name__ == '__main__':
    sys.exit(main(admin=True))
