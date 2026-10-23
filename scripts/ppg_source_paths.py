"""Shared source/private path classification for portable artifact inventories."""
from pathlib import PurePosixPath

PRIVATE_PARTS = {'.local', 'private', 'outputs', 'receipts', '.venv', 'node_modules', '__pycache__'}
PRIVATE_SUFFIXES = {'.xls', '.xlsx', '.xlsb', '.xlsm', '.msg', '.eml', '.pdf', '.docx',
                    '.zip', '.bundle', '.pem', '.pfx', '.key', '.pyc'}


def forbidden_path(name):
    path = PurePosixPath(name)
    if (path.is_absolute() or '..' in path.parts or '\\' in name
            or any(ord(c) < 32 or ord(c) == 127 for c in name)):
        return True
    if any(p.lower() in PRIVATE_PARTS for p in path.parts):
        return True
    if path.name.lower().startswith('.env') and path.name != '.env.example':
        return True
    return name.lower().endswith('.local.json') or path.suffix.lower() in PRIVATE_SUFFIXES
