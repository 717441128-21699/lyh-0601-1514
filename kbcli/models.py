import uuid
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


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
    reviewer: Optional[str] = None
    review_note: Optional[str] = None
    review_history: List[Dict[str, Any]] = field(default_factory=list)
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
            'reviewer': self.reviewer,
            'review_note': self.review_note,
            'review_history': self.review_history,
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
            reviewer=data.get('reviewer'),
            review_note=data.get('review_note'),
            review_history=data.get('review_history', []),
            created_at=data.get('created_at', datetime.now().isoformat()),
            updated_at=data.get('updated_at', datetime.now().isoformat()),
            last_accessed=data.get('last_accessed'),
            access_count=data.get('access_count', 0),
        )

    def touch(self):
        self.last_accessed = datetime.now().isoformat()
        self.access_count += 1

    def add_review_record(self, reviewer: str, note: str = '',
                         old_review: Optional[bool] = None,
                         old_expired: Optional[bool] = None,
                         new_review: Optional[bool] = None,
                         new_expired: Optional[bool] = None):
        record = {
            'timestamp': datetime.now().isoformat(),
            'reviewer': reviewer,
            'note': note,
        }
        changes = {}
        if old_review is not None and new_review is not None and old_review != new_review:
            changes['needs_review'] = {'old': old_review, 'new': new_review}
        if old_expired is not None and new_expired is not None and old_expired != new_expired:
            changes['expired'] = {'old': old_expired, 'new': new_expired}
        if changes:
            record['changes'] = changes
        self.review_history.insert(0, record)
        if len(self.review_history) > 20:
            self.review_history = self.review_history[:20]
