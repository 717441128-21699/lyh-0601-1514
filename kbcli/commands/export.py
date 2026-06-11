import click
import sys
import json
from pathlib import Path
from datetime import datetime

from ..config import find_kb_root, Config
from ..store import Store


@click.group('export')
def export_cmd():
    """导出知识库内容"""
    pass


@export_cmd.command('markdown')
@click.argument('output_dir', default='./export')
@click.option('--project', '-p', help='按项目导出')
@click.option('--tags', '-t', help='按标签过滤，多个用逗号分隔')
@click.option('--include-index/--no-index', default=True, help='是否生成目录索引')
@click.option('--expired', is_flag=True, help='包含过期条目')
def export_markdown(output_dir, project, tags, include_index, expired):
    """导出为 Markdown 文件"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]

    entries = store.list_entries(
        project=project,
        tags=tag_list if tag_list else None,
    )

    if not expired:
        entries = [e for e in entries if not e.expired]

    if not entries:
        click.echo('没有可导出的条目')
        return

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    project_map = {}
    for entry in entries:
        if entry.project not in project_map:
            project_map[entry.project] = []
        project_map[entry.project].append(entry)

    for proj, proj_entries in project_map.items():
        proj_dir = output_path / proj
        proj_dir.mkdir(parents=True, exist_ok=True)
        for entry in proj_entries:
            filename = _sanitize_filename(entry.title) + '.md'
            filepath = proj_dir / filename
            _write_entry_file(entry, filepath)

    if include_index:
        index_path = output_path / 'README.md'
        _write_index(entries, index_path, project)

    click.echo(f'已导出 {len(entries)} 条到 {output_dir}')


@export_cmd.command('json')
@click.argument('output_file', default='./export.json')
@click.option('--project', '-p', help='按项目导出')
@click.option('--tags', '-t', help='按标签过滤，多个用逗号分隔')
@click.option('--expired', is_flag=True, help='包含过期条目')
def export_json(output_file, project, tags, expired):
    """导出为 JSON 文件"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]

    entries = store.list_entries(
        project=project,
        tags=tag_list if tag_list else None,
    )

    if not expired:
        entries = [e for e in entries if not e.expired]

    if not entries:
        click.echo('没有可导出的条目')
        return

    data = {
        'exported_at': datetime.now().isoformat(),
        'count': len(entries),
        'entries': [e.to_dict() for e in entries],
    }

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    click.echo(f'已导出 {len(entries)} 条到 {output_file}')


@export_cmd.command('project')
@click.argument('project_name')
@click.argument('output_dir', default='./export')
def export_project(project_name, output_dir):
    """导出指定项目的所有内容"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entries = store.list_entries(project=project_name)

    if not entries:
        click.echo(f'项目 {project_name} 没有条目')
        return

    output_path = Path(output_dir) / project_name
    output_path.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        filename = _sanitize_filename(entry.title) + '.md'
        filepath = output_path / filename
        _write_entry_file(entry, filepath)

    index_path = output_path / 'README.md'
    _write_index(entries, index_path, project_name)

    click.echo(f'已导出项目 {project_name} 的 {len(entries)} 条到 {output_dir}/{project_name}')


@export_cmd.command('tag')
@click.argument('tag')
@click.argument('output_dir', default='./export')
def export_tag(tag, output_dir):
    """导出指定标签的所有内容"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entries = store.list_entries(tags=[tag])

    if not entries:
        click.echo(f'标签 {tag} 没有条目')
        return

    output_path = Path(output_dir) / f'tag-{_sanitize_filename(tag)}'
    output_path.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        filename = _sanitize_filename(entry.title) + '.md'
        filepath = output_path / filename
        _write_entry_file(entry, filepath)

    index_path = output_path / 'README.md'
    _write_index(entries, index_path, f'标签: {tag}')

    click.echo(f'已导出标签 {tag} 的 {len(entries)} 条到 {output_dir}')


def _sanitize_filename(name):
    import re
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = name.strip()
    if len(name) > 100:
        name = name[:100]
    return name or 'untitled'


def _write_entry_file(entry, filepath):
    import yaml
    frontmatter = {
        'id': entry.id,
        'title': entry.title,
        'project': entry.project,
        'tags': entry.tags,
        'created_at': entry.created_at,
        'updated_at': entry.updated_at,
    }
    if entry.ticket_links:
        frontmatter['ticket_links'] = entry.ticket_links
    if entry.links:
        frontmatter['links'] = entry.links
    if entry.expired:
        frontmatter['expired'] = True
    if entry.needs_review:
        frontmatter['needs_review'] = True

    fm_text = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)
    content = f'---\n{fm_text}---\n\n{entry.content}'

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def _write_index(entries, index_path, title='知识库'):
    lines = []
    lines.append(f'# {title} - 目录索引')
    lines.append('')
    lines.append(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append(f'总条目数: {len(entries)}')
    lines.append('')

    project_map = {}
    for entry in entries:
        if entry.project not in project_map:
            project_map[entry.project] = []
        project_map[entry.project].append(entry)

    for proj in sorted(project_map.keys()):
        proj_entries = project_map[proj]
        lines.append(f'## {proj} ({len(proj_entries)})')
        lines.append('')
        for entry in proj_entries:
            filename = _sanitize_filename(entry.title) + '.md'
            status = []
            if entry.expired:
                status.append('过期')
            if entry.needs_review:
                status.append('待复审')
            status_str = f' _[{", ".join(status)}]_' if status else ''
            tags_str = f' `{", ".join(entry.tags)}`' if entry.tags else ''
            lines.append(f'- [{entry.title}](./{proj}/{filename}){status_str}{tags_str}')
        lines.append('')

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
