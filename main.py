import builtins
from datetime import datetime
from pathlib import Path

from bot import main
from session_lock import exclusive_session

_original_print = builtins.print


def _print_with_datetime(*args, **kwargs):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _original_print(f"[{timestamp}]", *args, **kwargs)


builtins.print = _print_with_datetime

if __name__ == "__main__":
    try:
        with exclusive_session(Path(__file__).resolve().parent / 'stats' / 'controller.lock'):
            main()
    except (OSError, RuntimeError) as error:
        print(error)
