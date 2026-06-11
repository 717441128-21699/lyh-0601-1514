import os
import json
from pathlib import Path

KB_DIR_NAME = '.kb'
CONFIG_FILE = 'config.json'
INDEX_FILE = 'index.json'
HISTORY_FILE = 'history.json'
SHORTCUTS_FILE = 'shortcuts.json'
ENTRIES_DIR = 'entries'
PROJECTS_DIR = 'projects'


class Config:
    def __init__(self, kb_root):
        self.kb_root = Path(kb_root).resolve()
        self.kb_dir = self.kb_root / KB_DIR_NAME
        self.config_path = self.kb_dir / CONFIG_FILE
        self.index_path = self.kb_dir / INDEX_FILE
        self.history_path = self.kb_dir / HISTORY_FILE
        self.shortcuts_path = self.kb_dir / SHORTCUTS_FILE
        self.entries_dir = self.kb_dir / ENTRIES_DIR
        self.projects_dir = self.kb_dir / PROJECTS_DIR

    def is_initialized(self):
        return self.kb_dir.exists() and self.config_path.exists()

    def load_config(self):
        if not self.config_path.exists():
            return {}
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_config(self, config):
        self.kb_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)


def find_kb_root(start_path=None):
    if start_path is None:
        start_path = os.getcwd()
    current = Path(start_path).resolve()
    while True:
        if (current / KB_DIR_NAME).is_dir():
            return current
        parent = current.parent
        if parent == current:
            return None
        current = parent
