"""Entry point for the standalone Filter Generator (direct run and PyInstaller)."""
import sys
import os

# Ensure the package directory is on the path when run as a script
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from poe_price_trade.filter_gen_standalone import main

if __name__ == "__main__":
    main()
