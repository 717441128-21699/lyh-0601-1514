import click
import sys
import json
import re
from pathlib import Path
from datetime import datetime

from ..config import find_kb_root, Config
from ..store import Store


def _sanitize_filename(name):
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = name.strip()
    if len(name) > 100:
        name = name[:100]
    return name or 'untitled'


def _norm_path(p):
    """统一使用正斜杠路径，确保跨平台链接可点击。"""
    return str(p).replace('\\', '/')


def _write_entry_file(entry, filepath, include_meta=True):
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
    if entry.reviewer:
        frontmatter['reviewer'] = entry.reviewer
    if entry.review_note:
        frontmatter['review_note'] = entry.review_note
    if entry.last_accessed:
        frontmatter['last_accessed'] = entry.last_accessed
        frontmatter['access_count'] = entry.access_count

    fm_text = yaml.dump(frontmatter, allow_unicode=True, default_flow_style=False)
    content = f'---\n{fm_text}---\n\n'

    if include_meta:
        content += '## 基本信息\n\n'
        content += f'- **项目**: {entry.project}\n'
        if entry.tags:
            content += f'- **标签**: {", ".join(f"`{t}`" for t in entry.tags)}\n'
        content += f'- **创建时间**: {entry.created_at[:19]}\n'
        content += f'- **更新时间**: {entry.updated_at[:19]}\n'
        content += f'- **访问次数**: {entry.access_count}\n'
        if entry.last_accessed:
            content += f'- **最近访问**: {entry.last_accessed[:19]}\n'
        if entry.reviewer:
            content += f'- **负责人**: 👤 {entry.reviewer}\n'
        if entry.review_note:
            content += f'- **复审备注**: 📝 {entry.review_note}\n'

        statuses = []
        if entry.expired:
            statuses.append('🚫 已过期')
        if entry.needs_review:
            statuses.append('📋 待复审')
        if statuses:
            content += f'- **状态**: {", ".join(statuses)}\n'

        if entry.ticket_links:
            content += '\n### 关联工单\n\n'
            for tl in entry.ticket_links:
                content += f'- [{tl}]({tl})\n'

        if entry.links:
            content += '\n### 参考链接\n\n'
            for rl in entry.links:
                content += f'- {rl}\n'

        content += '\n---\n\n'

    content += entry.content
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)


def _get_status_badge(entry):
    badges = []
    if entry.expired:
        badges.append('🚫过期')
    if entry.needs_review:
        badges.append('📋待复审')
    return badges


def _write_change_summary(entries, output_dir, summary_path, filter_desc='',
                         include_expired=False):
    """生成导出变更摘要文档。"""
    lines = []
    lines.append(f'# 📦 知识库导出变更摘要')
    lines.append('')
    lines.append(f'> 导出时间: **{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**')
    if filter_desc:
        lines.append(f'> 导出过滤: **{filter_desc}**')
    lines.append(f'> 总条目数: **{len(entries)}**')
    lines.append('')

    lines.append('## 📊 本次导出概览')
    lines.append('')

    projects = sorted(set(e.project for e in entries))
    all_tags = sorted(set(t for e in entries for t in e.tags))
    expired = [e for e in entries if e.expired]
    need_review = [e for e in entries if e.needs_review]
    has_reviewer = [e for e in entries if e.reviewer]
    never_accessed = [e for e in entries if e.access_count == 0]
    total_access = sum(e.access_count for e in entries)

    lines.append(f'- 📁 导出项目: {len(projects)} 个  ')
    for p in projects:
        p_count = len([e for e in entries if e.project == p])
        p_expired = len([e for e in entries if e.project == p and e.expired])
        p_review = len([e for e in entries if e.project == p and e.needs_review])
        parts = [f'{p_count} 条']
        if p_expired:
            parts.append(f'🚫{p_expired} 过期')
        if p_review:
            parts.append(f'📋{p_review} 待复审')
        lines.append(f'  - **{p}**: {", ".join(parts)}')

    lines.append(f'- 🏷️  涉及标签: {len(all_tags)} 个 ({", ".join(all_tags)})')
    lines.append(f'- 🚫 过期内容: {len(expired)} 条')
    lines.append(f'- 📋 待复审: {len(need_review)} 条')
    lines.append(f'- 👤 已分配负责人: {len(has_reviewer)} 条')
    lines.append(f'- 🆕 从未访问: {len(never_accessed)} 条')
    lines.append(f'- 👥 累计访问: {total_access} 次')
    lines.append('')

    if need_review:
        lines.append('## ⚠️  待复审内容列表')
        lines.append('')
        lines.append('| # | 标题 | 项目 | 负责人 | 备注 | 更新时间 |')
        lines.append('|---|------|------|--------|------|----------|')
        for i, e in enumerate(need_review, 1):
            safe_title = _sanitize_filename(e.title)
            link_title = e.title.replace('|', '\\|')
            reviewer = e.reviewer or '-'
            note = e.review_note.replace('|', '\\|') if e.review_note else '-'
            if len(note) > 30:
                note = note[:30] + '...'
            rel_path = _norm_path(Path('.') / e.project / f'{safe_title}.md')
            lines.append(f'| {i} | [{link_title}]({rel_path}) | {e.project} | {reviewer} | {note} | {e.updated_at[:10]} |')
        lines.append('')

    if expired:
        lines.append('## 🚫 过期内容列表')
        lines.append('')
        lines.append('| # | 标题 | 项目 | 负责人 | 更新时间 |')
        lines.append('|---|------|------|--------|----------|')
        for i, e in enumerate(expired, 1):
            safe_title = _sanitize_filename(e.title)
            link_title = e.title.replace('|', '\\|')
            reviewer = e.reviewer or '-'
            rel_path = _norm_path(Path('.') / e.project / f'{safe_title}.md')
            lines.append(f'| {i} | [{link_title}]({rel_path}) | {e.project} | {reviewer} | {e.updated_at[:10]} |')
        lines.append('')

    if has_reviewer:
        lines.append('## 👤 按负责人分配')
        lines.append('')
        reviewer_map = {}
        for e in has_reviewer:
            if e.reviewer not in reviewer_map:
                reviewer_map[e.reviewer] = []
            reviewer_map[e.reviewer].append(e)
        for name in sorted(reviewer_map.keys()):
            reviewer_entries = reviewer_map[name]
            exp_count = len([e for e in reviewer_entries if e.expired])
            rev_count = len([e for e in reviewer_entries if e.needs_review])
            lines.append(f'### {name} (共 {len(reviewer_entries)} 条)')
            lines.append('')
            if exp_count or rev_count:
                parts = []
                if exp_count:
                    parts.append(f'🚫{exp_count} 过期')
                if rev_count:
                    parts.append(f'📋{rev_count} 待复审')
                lines.append(f'_ 状态: {", ".join(parts)} _')
                lines.append('')
            lines.append('| # | 标题 | 项目 | 状态 | 更新时间 |')
            lines.append('|---|------|------|------|----------|')
            for i, e in enumerate(reviewer_entries, 1):
                safe_title = _sanitize_filename(e.title)
                link_title = e.title.replace('|', '\\|')
                badges = _get_status_badge(e)
                status = ' '.join(badges) if badges else '✅'
                rel_path = _norm_path(Path('.') / e.project / f'{safe_title}.md')
                lines.append(f'| {i} | [{link_title}]({rel_path}) | {e.project} | {status} | {e.updated_at[:10]} |')
            lines.append('')

    lines.append('---')
    lines.append('')
    lines.append(f'> 🔗 详细目录请查看: [README.md](./README.md)')
    lines.append('')

    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def _write_team_index(entries, index_path, title='知识库', include_reviewer=True):
    lines = []
    lines.append(f'# 🏢 团队知识库 - {title}')
    lines.append('')
    lines.append(f'> 生成时间: **{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**')
    lines.append(f'> 总条目数: **{len(entries)}**')
    lines.append('')

    lines.append('## 📊 概览')
    lines.append('')

    expired = [e for e in entries if e.expired]
    need_review = [e for e in entries if e.needs_review]
    never_accessed = [e for e in entries if e.access_count == 0]
    total_access = sum(e.access_count for e in entries)
    reviewers = sorted(set(e.reviewer for e in entries if e.reviewer))
    lines.append(f'- 📁 项目分类: {len(set(e.project for e in entries))} 个')
    lines.append(f'- 🏷️  标签总数: {len(set(t for e in entries for t in e.tags))} 个')
    lines.append(f'- 🚫 过期条目: {len(expired)} 条')
    lines.append(f'- 📋 待复审: {len(need_review)} 条')
    if reviewers:
        lines.append(f'- 👤 负责人: {", ".join(reviewers)}')
    lines.append(f'- 🆕 从未访问: {len(never_accessed)} 条')
    lines.append(f'- 👥 累计访问: {total_access} 次')
    lines.append('')

    lines.append('## 📑 详细目录')
    lines.append('')

    project_map = {}
    for entry in entries:
        if entry.project not in project_map:
            project_map[entry.project] = []
        project_map[entry.project].append(entry)

    for proj in sorted(project_map.keys()):
        proj_entries = sorted(project_map[proj], key=lambda e: e.updated_at, reverse=True)
        proj_expired = len([e for e in proj_entries if e.expired])
        proj_review = len([e for e in proj_entries if e.needs_review])
        lines.append(f'### 📁 {proj}')
        lines.append('')
        meta_parts = [f'共 {len(proj_entries)} 条']
        if proj_expired:
            meta_parts.append(f'🚫{proj_expired} 过期')
        if proj_review:
            meta_parts.append(f'📋{proj_review} 待复审')
        lines.append(f'_ {" | ".join(meta_parts)} _')
        lines.append('')

        header_cols = ['#', '标题', '标签', '状态']
        if include_reviewer:
            header_cols.append('负责人')
        header_cols.extend(['更新时间', '访问', '最近访问'])
        lines.append('| ' + ' | '.join(header_cols) + ' |')
        lines.append('|' + '|'.join('---' for _ in header_cols) + '|')

        for i, e in enumerate(proj_entries, 1):
            badges = _get_status_badge(e)
            tags_md = ', '.join(f'`{t}`' for t in e.tags) if e.tags else '-'
            status_md = ' '.join(badges) if badges else '✅'
            updated = e.updated_at[:10]
            accessed = f'{e.access_count}次'
            last = e.last_accessed[:10] if e.last_accessed else '从未'
            safe_title = _sanitize_filename(e.title)
            link_title = e.title.replace('|', '\\|')
            rel_path = _norm_path(Path('.') / proj / f'{safe_title}.md')

            row = [str(i), f'[{link_title}]({rel_path})', tags_md, status_md]
            if include_reviewer:
                reviewer = f'👤 {e.reviewer}' if e.reviewer else '-'
                row.append(reviewer)
            row.extend([updated, accessed, last])
            lines.append('| ' + ' | '.join(row) + ' |')
        lines.append('')

    lines.append('---')
    lines.append('')
    lines.append('## 📝 状态说明')
    lines.append('')
    lines.append('- ✅ 正常条目')
    lines.append('- 🚫过期 - 内容已过期，建议更新或删除')
    lines.append('- 📋待复审 - 需要团队成员复核内容准确性')
    lines.append('')

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


@click.group('export')
def export_cmd():
    """导出知识库内容（支持包含过期内容、访问统计、团队索引、变更摘要）"""
    pass


@export_cmd.command('markdown')
@click.argument('output_dir', default='./export')
@click.option('--project', '-p', help='按项目导出')
@click.option('--tags', '-t', help='按标签过滤，多个用逗号分隔')
@click.option('--include-index/--no-index', default=True, help='是否生成目录索引')
@click.option('--include-expired/--exclude-expired', default=False, help='是否包含过期条目')
@click.option('--include-meta/--no-meta', default=True, help='是否包含访问统计和复审状态')
@click.option('--team-index/--simple-index', default=True, help='生成团队浏览的索引文件')
@click.option('--include-summary/--no-summary', default=True, help='是否生成变更摘要')
@click.option('--include-reviewer/--no-reviewer', default=True, help='索引中包含负责人信息')
def export_markdown(output_dir, project, tags, include_index, include_expired, include_meta,
                    team_index, include_summary, include_reviewer):
    """导出为 Markdown 文件（可包含过期内容、访问统计、变更摘要）。"""
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

    excluded_expired = 0
    if not include_expired:
        excluded_expired = len([e for e in entries if e.expired])
        entries = [e for e in entries if not e.expired]
        if excluded_expired > 0:
            click.echo(f'已排除 {excluded_expired} 条过期内容（使用 --include-expired 可包含）')

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
            _write_entry_file(entry, filepath, include_meta=include_meta)

    index_path = None
    if include_index:
        index_path = output_path / 'README.md'
        if team_index:
            title_parts = []
            if project:
                title_parts.append(f'项目: {project}')
            if tag_list:
                title_parts.append(f'标签: {", ".join(tag_list)}')
            if not include_expired:
                title_parts.append('不含过期')
            title = ' / '.join(title_parts) if title_parts else '全库'
            _write_team_index(entries, index_path, title=title, include_reviewer=include_reviewer)
        else:
            _write_simple_index(entries, index_path, project or '知识库')

    if include_summary:
        summary_path = output_path / 'CHANGELOG.md'
        filter_parts = []
        if project:
            filter_parts.append(f'项目={project}')
        if tag_list:
            filter_parts.append(f'标签={",".join(tag_list)}')
        if not include_expired:
            filter_parts.append('不含过期')
        filter_desc = ' | '.join(filter_parts) if filter_parts else '全库导出'
        _write_change_summary(
            entries,
            output_dir=output_path,
            summary_path=summary_path,
            filter_desc=filter_desc,
            include_expired=include_expired,
        )

    click.echo(f'✅ 已导出 {len(entries)} 条到 {output_dir}')
    if include_expired:
        exp_count = len([e for e in entries if e.expired])
        if exp_count:
            click.echo(f'   其中包含 {exp_count} 条过期内容')
    if include_index:
        click.echo(f'   索引文件: {_norm_path(index_path)}')
    if include_summary:
        click.echo(f'   变更摘要: {_norm_path(output_path / "CHANGELOG.md")}')


@export_cmd.command('json')
@click.argument('output_file', default='./export.json')
@click.option('--project', '-p', help='按项目导出')
@click.option('--tags', '-t', help='按标签过滤，多个用逗号分隔')
@click.option('--include-expired/--exclude-expired', default=False, help='是否包含过期条目')
@click.option('--include-meta/--no-meta', default=True, help='是否包含访问统计和复审状态')
def export_json(output_file, project, tags, include_expired, include_meta):
    """导出为 JSON 文件（可包含过期、状态、访问统计）。"""
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

    if not include_expired:
        entries = [e for e in entries if not e.expired]

    if not entries:
        click.echo('没有可导出的条目')
        return

    entries_data = []
    for e in entries:
        data = e.to_dict()
        if not include_meta:
            data.pop('last_accessed', None)
            data.pop('access_count', None)
            data.pop('reviewer', None)
            data.pop('review_note', None)
            data.pop('review_history', None)
        entries_data.append(data)

    data = {
        'exported_at': datetime.now().isoformat(),
        'count': len(entries),
        'include_expired': include_expired,
        'entries': entries_data,
    }

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    click.echo(f'✅ 已导出 {len(entries)} 条到 {output_file}')


@export_cmd.command('project')
@click.argument('project_name')
@click.argument('output_dir', default='./export')
@click.option('--include-expired/--exclude-expired', default=False, help='是否包含过期条目')
@click.option('--include-meta/--no-meta', default=True, help='是否包含访问统计和复审状态')
@click.option('--include-summary/--no-summary', default=True, help='是否生成变更摘要')
@click.option('--include-reviewer/--no-reviewer', default=True, help='索引中包含负责人信息')
def export_project(project_name, output_dir, include_expired, include_meta, include_summary, include_reviewer):
    """导出指定项目的所有内容（生成团队友好索引 + 变更摘要）。"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entries = store.list_entries(project=project_name)

    if not include_expired:
        entries = [e for e in entries if not e.expired]

    if not entries:
        click.echo(f'项目 {project_name} 没有匹配的条目')
        return

    output_path = Path(output_dir) / project_name
    output_path.mkdir(parents=True, exist_ok=True)

    for entry in entries:
        filename = _sanitize_filename(entry.title) + '.md'
        filepath = output_path / filename
        _write_entry_file(entry, filepath, include_meta=include_meta)

    index_path = output_path / 'README.md'
    _write_team_index(entries, index_path, title=f'项目: {project_name}', include_reviewer=include_reviewer)

    if include_summary:
        summary_path = output_path / 'CHANGELOG.md'
        filter_desc = f'项目={project_name}'
        if not include_expired:
            filter_desc += ' | 不含过期'
        _write_change_summary(
            entries,
            output_dir=output_path,
            summary_path=summary_path,
            filter_desc=filter_desc,
            include_expired=include_expired,
        )

    click.echo(f'✅ 已导出项目 {project_name} 的 {len(entries)} 条到 {_norm_path(output_path)}')
    click.echo(f'   索引文件: {_norm_path(index_path)}')
    if include_summary:
        click.echo(f'   变更摘要: {_norm_path(output_path / "CHANGELOG.md")}')


@export_cmd.command('tag')
@click.argument('tag_name')
@click.argument('output_dir', default='./export')
@click.option('--include-expired/--exclude-expired', default=False, help='是否包含过期条目')
@click.option('--include-meta/--no-meta', default=True, help='是否包含访问统计和复审状态')
@click.option('--include-summary/--no-summary', default=True, help='是否生成变更摘要')
@click.option('--include-reviewer/--no-reviewer', default=True, help='索引中包含负责人信息')
def export_tag(tag_name, output_dir, include_expired, include_meta, include_summary, include_reviewer):
    """导出指定标签的所有内容（生成团队友好索引 + 变更摘要）。"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entries = store.list_entries(tags=[tag_name])

    if not include_expired:
        entries = [e for e in entries if not e.expired]

    if not entries:
        click.echo(f'标签 {tag_name} 没有匹配的条目')
        return

    output_path = Path(output_dir) / f'tag-{_sanitize_filename(tag_name)}'
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
            _write_entry_file(entry, filepath, include_meta=include_meta)

    index_path = output_path / 'README.md'
    _write_team_index(entries, index_path, title=f'标签: {tag_name}', include_reviewer=include_reviewer)

    if include_summary:
        summary_path = output_path / 'CHANGELOG.md'
        filter_desc = f'标签={tag_name}'
        if not include_expired:
            filter_desc += ' | 不含过期'
        _write_change_summary(
            entries,
            output_dir=output_path,
            summary_path=summary_path,
            filter_desc=filter_desc,
            include_expired=include_expired,
        )

    click.echo(f'✅ 已导出标签 {tag_name} 的 {len(entries)} 条到 {_norm_path(output_path)}')
    click.echo(f'   索引文件: {_norm_path(index_path)}')
    if include_summary:
        click.echo(f'   变更摘要: {_norm_path(output_path / "CHANGELOG.md")}')


def _write_simple_index(entries, index_path, title='知识库'):
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
            rel_path = _norm_path(Path('.') / proj / filename)
            lines.append(f'- [{entry.title}]({rel_path}){status_str}{tags_str}')
        lines.append('')

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
