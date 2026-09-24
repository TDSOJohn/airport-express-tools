try:
    from .cli import main
except ImportError:
    # Allow `python3 airportctl` or `python3 airportctl/__main__.py` (run as a loose script with
    # no package context) by putting the package's parent dir on sys.path and importing by name.
    import os
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from airportctl.cli import main

if __name__ == '__main__':
    main()
