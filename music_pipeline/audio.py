import subprocess
import sys
from typing import Optional

_current_process: Optional[subprocess.Popen] = None


def play(file_path: str):
    """Play an audio file using the system player."""
    global _current_process
    stop()

    if sys.platform == "darwin":
        cmd = ["afplay", file_path]
    elif sys.platform.startswith("linux"):
        # Try common Linux players in order
        for player in ["mpv", "ffplay", "aplay", "paplay"]:
            result = subprocess.run(["which", player], capture_output=True)
            if result.returncode == 0:
                cmd = [player, file_path]
                break
        else:
            return
    else:
        return

    _current_process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop():
    """Stop any currently playing audio."""
    global _current_process
    if _current_process and _current_process.poll() is None:
        _current_process.terminate()
        _current_process = None
