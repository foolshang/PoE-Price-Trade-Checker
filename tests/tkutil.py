"""Tk for the tests. On this machine (Windows Store Python) creating a Tk root now and then fails with
"couldn't read file .../tcl8.6/init.tcl: No error" (a transient read failure of the interpreter's own Tcl files,
about one run in four of tests/test_filter_gen_standalone.py): the same call succeeds a moment later, so try a few
times before the fixture gives up and skips."""
from __future__ import annotations
import time
import tkinter as tk


def new_root(attempts: int = 6, wait: float = 0.25) -> tk.Tk:
    last = None
    for _ in range(attempts):
        try:
            return tk.Tk()
        except tk.TclError as e:
            last = e
            time.sleep(wait)
    raise last
