#!/usr/bin/env python3
"""Read-only local pilot entry point; one JSON request on stdin."""
import sys
sys.dont_write_bytecode = True
from wiki_access.cli import main

if __name__ == '__main__':
    sys.exit(main())
