import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional


def generate_id():
    return uuid.uuid4().hex[:12]


@dataclass
class Entry:
    id: str
    title: str
    content: str
    project: str = 'default'
    tags: List[str] = field(default_factory=list)
    links: List[str] = field(default_factory=list)
    ticket_links: List[str] = field(default_factory=list)
    expired: bool = False
    needs_review: bool = False
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_accessed: Optional[str] = None
    access_count: int = 0

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'content': self.content,
            'project': self.project,
            'tags': self.tags,
            'links': self.links,
            'ticket_links': self.ticket_links,
            'expired': self.expired,
            'needs_review': self.needs_review,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
            'last_accessed': self.last_accessed,
            'access_count': self.access_count,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get('id', generate_id()),
            title=data.get('title', ''),
            content=data.get('content', ''),
            project=data.get('project', 'default'),
            tags=data.get('tags', []),
            links=data.get('links', []),
            ticket_links=data.get('ticket_links', []),
            expired=data.get('expired', False),
            needs_review=data.get('needs_review', False),
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat()),
            last_accessed=data.get('last_accessed'),
            access_count=data.get('access_count', 0),
        )

    def touch(self):
        self.last_accessed = datetime.now().isoformat()
        self.access_count += 1
