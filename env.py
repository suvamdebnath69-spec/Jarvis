"""Tiny .env loader.

Reads `.env` from the project folder (next to this file) into os.environ so
API keys and settings can be pasted into a plain text file instead of Windows
environment variables. Real environment variables always win.

Format:  KEY=VALUE  (one per line, # for comments, quotes stripped)
"""

import os


def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    seen = set()
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if not key:
                    continue
                # A real Windows/user env var always wins over the .env file.
                if key in os.environ and key not in seen:
                    continue
                # Skip empty placeholder lines ("KEY=") until a value appears;
                # later lines in the file override earlier ones.
                if not value and key not in seen:
                    continue
                seen.add(key)
                os.environ[key] = value
    except OSError:
        pass  # no .env file - use whatever is in the environment
