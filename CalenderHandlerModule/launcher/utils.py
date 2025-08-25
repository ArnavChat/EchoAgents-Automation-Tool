import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Project root
ROOT = Path(__file__).resolve().parent.parent.parent

def get_path(relative_path):
    return ROOT / relative_path

def get_env(key, default=None):
    return os.getenv(key, default)
