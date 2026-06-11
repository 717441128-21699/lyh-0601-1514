import os
import json
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

from .config import Config
from .models import Entry, generate_id


class Store:
    def __init__(self, config: Config):
        self.config = config
        self._index: Optional[Dict[str, Entry]] = None

    def _ensure_dirs(self):
        self.config.entries_dir.mkdir(parents=True, exist_ok=True)
        self.config.projects_dir.mkdir(parents=True, exist_ok=True)

    def load_index(self) -> Dict[str, Entry]:
        if self._index is not None:
            return self._index
        if not self.config.index_path.exists():
            self._index = {}
            return self._index
        with open(self.config.index_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self._index = {k: Entry.from_dict(v) for k, v in data.items()}
        return self._index

    def save_index(self):
        if self._index is None:
            return
        self._ensure_dirs()
        data = {k: v.to_dict() for k, v in self._index.items()}
        with open(self.config.index_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_entry(self, entry: Entry) -> Entry:
        index = self.load_index()
        if not entry.id:
            entry.id = generate_id()
        entry.created_at = datetime.now().isoformat()
        entry.updated_at = entry.created_at
        index[entry.id] = entry
        self._save_entry_file(entry)
        self._update_project_index(entry)
        self.save_index()
        return entry

    def get_entry(self, entry_id: str) -> Optional[Entry]:
        index = self.load_index()
        return index.get(entry_id)

    def resolve_entry(self, entry_id: str) -> Optional[Entry]:
        """根据ID解析条目，支持完整ID和前缀匹配。

        返回 (entry, error_message) 元组：
        - 找到唯一匹配：(entry, None)
        - 未找到：(None, 错误提示)
        - 多个匹配：(None, 列出所有匹配的提示)
        """
        index = self.load_index()
        if not index:
            return None, '知识库为空，没有任何条目'

        if entry_id in index:
            return index[entry_id], None

        candidates = [e for eid, e in index.items() if eid.startswith(entry_id)]

        if len(candidates) == 0:
            return None, (
                f'未找到ID为 "{entry_id}" 的条目。\n'
                f'提示：请确认输入的ID是否正确，或使用 `kb list` 查看所有条目。'
            )
        elif len(candidates) == 1:
            return candidates[0], None
        else:
            lines = [f'ID "{entry_id}" 匹配到多个条目，请使用更长的前缀：']
            for e in candidates:
                lines.append(f'  {e.id}  {e.title}')
            return None, '\n'.join(lines)

    def update_entry(self, entry: Entry) -> Entry:
        index = self.load_index()
        entry.updated_at = datetime.now().isoformat()
        index[entry.id] = entry
        self._save_entry_file(entry)
        self._update_project_index(entry)
        self.save_index()
        return entry

    def delete_entry(self, entry_id: str) -> bool:
        index = self.load_index()
        if entry_id not in index:
            return False
        entry = index[entry_id]
        entry_file = self._get_entry_filepath(entry)
        if entry_file.exists():
            entry_file.unlink()
        del index[entry_id]
        self.save_index()
        return True

    def list_entries(self, project: Optional[str] = None,
                     tags: Optional[List[str]] = None,
                     expired: Optional[bool] = None,
                     needs_review: Optional[bool] = None) -> List[Entry]:
        index = self.load_index()
        entries = list(index.values())
        if project:
            entries = [e for e in entries if e.project == project]
        if tags:
            tag_set = set(tags)
            entries = [e for e in entries if tag_set.issubset(set(e.tags))]
        if expired is not None:
            entries = [e for e in entries if e.expired == expired]
        if needs_review is not None:
            entries = [e for e in entries if e.needs_review == needs_review]
        return entries

    def search_entries(self, keyword: str,
                       project: Optional[str] = None,
                       tags: Optional[List[str]] = None) -> List[Entry]:
        entries = self.list_entries(project=project, tags=tags)
        keyword_lower = keyword.lower()
        results = []
        for entry in entries:
            score = 0
            if keyword_lower in entry.title.lower():
                score += 10
            if keyword_lower in entry.content.lower():
                score += 5
            for tag in entry.tags:
                if keyword_lower in tag.lower():
                    score += 3
            if score > 0:
                results.append((score, entry))
        results.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in results]

    def record_access(self, entry_id: str):
        entry = self.get_entry(entry_id)
        if entry:
            entry.touch()
            self.update_entry(entry)
        history = self.load_history()
        history.insert(0, {
            'entry_id': entry_id,
            'accessed_at': datetime.now().isoformat(),
        })
        history = history[:50]
        self._save_history(history)

    def load_history(self) -> List[Dict]:
        if not self.config.history_path.exists():
            return []
        with open(self.config.history_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_history(self, history: List[Dict]):
        self._ensure_dirs()
        with open(self.config.history_path, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)

    def load_shortcuts(self) -> Dict[str, Dict]:
        if not self.config.shortcuts_path.exists():
            return {}
        with open(self.config.shortcuts_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_shortcut(self, name: str, command: str, description: str = '',
                      args: Optional[List[str]] = None, group: str = 'default'):
        shortcuts = self.load_shortcuts()
        data = {
            'command': command,
            'description': description,
            'group': group,
            'created_at': datetime.now().isoformat(),
        }
        if args is not None:
            data['args'] = args
        shortcuts[name] = data
        self._ensure_dirs()
        with open(self.config.shortcuts_path, 'w', encoding='utf-8') as f:
            json.dump(shortcuts, f, ensure_ascii=False, indent=2)

    def save_shortcuts(self, shortcuts_data: Dict[str, Dict], overwrite: bool = False):
        """批量保存快捷命令，用于导入。"""
        if overwrite:
            data = shortcuts_data
        else:
            existing = self.load_shortcuts()
            existing.update(shortcuts_data)
            data = existing
        self._ensure_dirs()
        with open(self.config.shortcuts_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def delete_shortcut(self, name: str) -> bool:
        shortcuts = self.load_shortcuts()
        if name not in shortcuts:
            return False
        del shortcuts[name]
        self._ensure_dirs()
        with open(self.config.shortcuts_path, 'w', encoding='utf-8') as f:
            json.dump(shortcuts, f, ensure_ascii=False, indent=2)
        return True

    # ---- Saved Query Templates ----
    def load_templates(self) -> Dict[str, Dict]:
        if not self.config.templates_path.exists():
            return {}
        with open(self.config.templates_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_template(self, name: str, template: Dict):
        templates = self.load_templates()
        data = dict(template)
        data['created_at'] = datetime.now().isoformat()
        templates[name] = data
        self._ensure_dirs()
        with open(self.config.templates_path, 'w', encoding='utf-8') as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)

    def delete_template(self, name: str) -> bool:
        templates = self.load_templates()
        if name not in templates:
            return False
        del templates[name]
        self._ensure_dirs()
        with open(self.config.templates_path, 'w', encoding='utf-8') as f:
            json.dump(templates, f, ensure_ascii=False, indent=2)
        return True

    def save_templates(self, templates_data: Dict[str, Dict], overwrite: bool = False):
        if overwrite:
            data = templates_data
        else:
            existing = self.load_templates()
            existing.update(templates_data)
            data = existing
        self._ensure_dirs()
        with open(self.config.templates_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def list_projects(self) -> List[str]:
        index = self.load_index()
        projects = set()
        for entry in index.values():
            projects.add(entry.project)
        return sorted(list(projects))

    def list_all_tags(self) -> List[str]:
        index = self.load_index()
        tags = set()
        for entry in index.values():
            tags.update(entry.tags)
        return sorted(list(tags))

    def _get_entry_filepath(self, entry: Entry) -> Path:
        project_dir = self.config.projects_dir / entry.project
        project_dir.mkdir(parents=True, exist_ok=True)
        return project_dir / f'{entry.id}.md'

    def _save_entry_file(self, entry: Entry):
        filepath = self._get_entry_filepath(entry)
        frontmatter = self._build_frontmatter(entry)
        content = f'---\n{frontmatter}---\n\n{entry.content}'
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    def _build_frontmatter(self, entry: Entry) -> str:
        import yaml
        data = {
            'id': entry.id,
            'title': entry.title,
            'project': entry.project,
            'tags': entry.tags,
            'links': entry.links,
            'ticket_links': entry.ticket_links,
            'expired': entry.expired,
            'needs_review': entry.needs_review,
            'reviewer': entry.reviewer,
            'review_note': entry.review_note,
            'created_at': entry.created_at,
            'updated_at': entry.updated_at,
        }
        return yaml.dump(data, allow_unicode=True, default_flow_style=False)

    def _update_project_index(self, entry: Entry):
        pass

    def check_broken_links(self) -> List[Dict]:
        from .commands.link import extract_url
        import urllib.request
        import urllib.error
        index = self.load_index()
        broken = []
        for entry in index.values():
            all_links = entry.links + entry.ticket_links
            for link in all_links:
                url = extract_url(link)
                try:
                    if url.startswith('http://') or url.startswith('https://'):
                        req = urllib.request.Request(url, method='HEAD')
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            if resp.status >= 400:
                                broken.append({
                                    'entry_id': entry.id,
                                    'entry_title': entry.title,
                                    'link': link,
                                    'status': resp.status,
                                })
                except Exception as e:
                    broken.append({
                        'entry_id': entry.id,
                        'entry_title': entry.title,
                        'link': link,
                        'error': str(e),
                    })
        return broken
