import click
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path
import os

from ..config import find_kb_root, Config
from ..store import Store


def _get_default_reviewer():
    """获取默认负责人（从环境变量或系统用户名）。"""
    return os.environ.get('KB_REVIEWER') or os.environ.get('USER') or os.environ.get('USERNAME') or 'unknown'


@click.group('review')
def review_cmd():
    """内容复审管理（支持备注、负责人、历史记录）"""
    pass


@review_cmd.command('list')
@click.option('--project', '-p', help='按项目过滤')
@click.option('--reviewer', '-r', help='按负责人过滤')
@click.option('--limit', '-n', type=int, default=20, help='显示数量限制')
def list_review(project, reviewer, limit):
    """列出待复审的条目（显示负责人和备注）"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entries = store.list_entries(project=project, needs_review=True)

    if reviewer:
        entries = [e for e in entries if e.reviewer == reviewer]

    if not entries:
        click.echo('没有待复审的条目')
        return

    entries = entries[:limit]

    click.echo(f'共 {len(entries)} 条待复审 (显示前 {limit} 条):')
    click.echo('-' * 70)
    for entry in entries:
        click.echo(f'{entry.id[:8]}  {entry.title}')
        click.echo(f'        项目: {entry.project} | 更新: {entry.updated_at[:10]}')
        if entry.tags:
            click.echo(f'        标签: {", ".join(entry.tags)}')
        if entry.reviewer:
            click.echo(f'        负责人: 👤 {entry.reviewer}')
        if entry.review_note:
            note_preview = entry.review_note[:50] + '...' if len(entry.review_note) > 50 else entry.review_note
            click.echo(f'        备注: 📝 {note_preview}')
        click.echo()


@review_cmd.command('mark')
@click.argument('entry_id')
@click.option('--review', type=click.Choice(['true', 'false']), help='标记待复审状态')
@click.option('--expired', type=click.Choice(['true', 'false']), help='标记过期状态')
@click.option('--reviewer', '-r', help='负责人名称（默认从环境变量 KB_REVIEWER 读取）')
@click.option('--note', '-m', help='备注信息')
@click.option('--no-history', is_flag=True, help='不记录此次变更历史')
def mark_entry(entry_id, review, expired, reviewer, note, no_history):
    """标记条目状态（支持备注和负责人，记录变更历史）。"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entry, err = store.resolve_entry(entry_id)
    if err:
        click.echo(f'错误: {err}', err=True)
        sys.exit(1)

    old_review = entry.needs_review
    old_expired = entry.expired

    if review is not None:
        entry.needs_review = review == 'true'
    if expired is not None:
        entry.expired = expired == 'true'

    if reviewer is not None:
        entry.reviewer = reviewer
    elif not entry.reviewer:
        entry.reviewer = _get_default_reviewer()

    if note:
        entry.review_note = note

    if not no_history and (review is not None or expired is not None or note or reviewer):
        entry.add_review_record(
            reviewer=entry.reviewer or _get_default_reviewer(),
            note=note or '',
            old_review=old_review,
            old_expired=old_expired,
            new_review=entry.needs_review,
            new_expired=entry.expired,
        )

    store.update_entry(entry)

    status = []
    if entry.needs_review:
        status.append('待复审')
    if entry.expired:
        status.append('过期')
    click.echo(f'条目已标记: {entry.title} ({entry.id})')
    click.echo(f'  当前状态: {", ".join(status) if status else "无特殊标记"}')
    if entry.reviewer:
        click.echo(f'  负责人: 👤 {entry.reviewer}')
    if entry.review_note:
        click.echo(f'  备注: 📝 {entry.review_note}')


@review_cmd.command('history')
@click.argument('entry_id')
@click.option('--limit', '-n', type=int, default=10, help='显示最近N条记录')
def show_history(entry_id, limit):
    """查看条目的复审历史记录"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entry, err = store.resolve_entry(entry_id)
    if err:
        click.echo(f'错误: {err}', err=True)
        sys.exit(1)

    if not entry.review_history:
        click.echo(f'条目 "{entry.title}" 暂无复审历史记录')
        return

    history = entry.review_history[:limit]
    click.echo(f'条目: {entry.title} ({entry.id})')
    click.echo(f'复审历史 (最近 {len(history)} 条):')
    click.echo('-' * 70)
    for i, record in enumerate(history, 1):
        ts = record.get('timestamp', '')[:19]
        reviewer = record.get('reviewer', 'unknown')
        note = record.get('note', '')
        click.echo(f'{i:2d}. [{ts}] 👤 {reviewer}')
        if note:
            click.echo(f'    📝 {note}')
        changes = record.get('changes', {})
        if changes:
            for field, change in changes.items():
                old_val = '是' if change.get('old') else '否'
                new_val = '是' if change.get('new') else '否'
                field_cn = {'needs_review': '待复审', 'expired': '过期'}
                click.echo(f'    🔄 {field_cn.get(field, field)}: {old_val} → {new_val}')
        click.echo()


@review_cmd.command('expired')
@click.option('--project', '-p', help='按项目过滤')
@click.option('--limit', '-n', type=int, default=20, help='显示数量限制')
def list_expired(project, limit):
    """列出过期的条目"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entries = store.list_entries(project=project, expired=True)

    if not entries:
        click.echo('没有过期的条目')
        return

    entries = entries[:limit]

    click.echo(f'共 {len(entries)} 条过期 (显示前 {limit} 条):')
    click.echo('-' * 70)
    for entry in entries:
        click.echo(f'{entry.id[:8]}  {entry.title}')
        click.echo(f'        项目: {entry.project} | 更新: {entry.updated_at[:10]}')
        if entry.reviewer:
            click.echo(f'        负责人: 👤 {entry.reviewer}')
        if entry.review_note:
            note_preview = entry.review_note[:50] + '...' if len(entry.review_note) > 50 else entry.review_note
            click.echo(f'        备注: 📝 {note_preview}')


@review_cmd.command('stale')
@click.option('--days', '-d', type=int, default=180, help='多少天未更新视为陈旧')
@click.option('--project', '-p', help='按项目过滤')
@click.option('--limit', '-n', type=int, default=20, help='显示数量限制')
def list_stale(days, project, limit):
    """列出长期未更新的陈旧条目"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entries = store.list_entries(project=project)
    cutoff = datetime.now() - timedelta(days=days)

    stale_entries = []
    for entry in entries:
        try:
            updated = datetime.fromisoformat(entry.updated_at)
            if updated < cutoff:
                stale_entries.append((updated, entry))
        except:
            pass

    stale_entries.sort(key=lambda x: x[0])

    if not stale_entries:
        click.echo(f'没有超过 {days} 天未更新的条目')
        return

    stale_entries = stale_entries[:limit]

    click.echo(f'共 {len(stale_entries)} 条陈旧条目 (显示前 {limit} 条):')
    click.echo('-' * 70)
    for updated, entry in stale_entries:
        days_old = (datetime.now() - updated).days
        click.echo(f'{entry.id[:8]}  {entry.title}')
        click.echo(f'        项目: {entry.project} | {days_old} 天未更新')
        if entry.reviewer:
            click.echo(f'        负责人: 👤 {entry.reviewer}')


@review_cmd.command('index')
@click.option('--output', '-o', help='输出文件路径，默认输出到标准输出')
@click.option('--project', '-p', help='按项目生成索引')
@click.option('--group-by-tag', is_flag=True, help='按标签分组')
@click.option('--include-reviewer/--no-reviewer', default=True, help='索引中包含负责人信息')
def generate_index(output, project, group_by_tag, include_reviewer):
    """生成目录索引（包含负责人和复审状态）"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entries = store.list_entries(project=project)

    if not entries:
        click.echo('没有条目')
        return

    lines = []
    lines.append('# 知识库目录索引')
    lines.append('')
    lines.append(f'生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    lines.append(f'总条目数: {len(entries)}')
    lines.append('')

    if group_by_tag:
        tag_map = {}
        for entry in entries:
            if not entry.tags:
                if '未分类' not in tag_map:
                    tag_map['未分类'] = []
                tag_map['未分类'].append(entry)
            else:
                for tag in entry.tags:
                    if tag not in tag_map:
                        tag_map[tag] = []
                    tag_map[tag].append(entry)

        for tag in sorted(tag_map.keys()):
            lines.append(f'## {tag} ({len(tag_map[tag])})')
            lines.append('')
            for entry in tag_map[tag]:
                status = []
                if entry.expired:
                    status.append('过期')
                if entry.needs_review:
                    status.append('待复审')
                status_str = f' _[{ ", ".join(status)}]_' if status else ''
                lines.append(f'- **{entry.title}**{status_str}')
                lines.append(f'  - ID: `{entry.id}`')
                lines.append(f'  - 项目: {entry.project}')
                lines.append(f'  - 更新: {entry.updated_at[:10]}')
                if entry.tags:
                    lines.append(f'  - 标签: {", ".join(entry.tags)}')
                if include_reviewer and entry.reviewer:
                    lines.append(f'  - 负责人: 👤 {entry.reviewer}')
                if include_reviewer and entry.review_note:
                    lines.append(f'  - 备注: 📝 {entry.review_note}')
            lines.append('')
    else:
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
                status = []
                if entry.expired:
                    status.append('过期')
                if entry.needs_review:
                    status.append('待复审')
                status_str = f' _[{ ", ".join(status)}]_' if status else ''
                tags_str = f' [{", ".join(entry.tags)}]' if entry.tags else ''
                reviewer_str = f' 👤 {entry.reviewer}' if include_reviewer and entry.reviewer else ''
                lines.append(f'- **{entry.title}**{status_str}{tags_str}{reviewer_str}')
                lines.append(f'  - ID: `{entry.id}`')
                lines.append(f'  - 更新: {entry.updated_at[:10]}')
                if include_reviewer and entry.review_note:
                    lines.append(f'  - 备注: 📝 {entry.review_note}')
            lines.append('')

    content = '\n'.join(lines)

    if output:
        with open(output, 'w', encoding='utf-8') as f:
            f.write(content)
        click.echo(f'目录索引已生成: {output}')
    else:
        click.echo(content)


@review_cmd.command('stats')
@click.option('--by-reviewer', is_flag=True, help='按负责人统计')
def stats(by_reviewer):
    """显示知识库统计信息"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    all_entries = store.list_entries()
    projects = store.list_projects()
    tags = store.list_all_tags()
    expired_entries = store.list_entries(expired=True)
    review_entries = store.list_entries(needs_review=True)
    history = store.load_history()

    click.echo('知识库统计')
    click.echo('=' * 50)
    click.echo(f'总条目数: {len(all_entries)}')
    click.echo(f'项目数: {len(projects)}')
    click.echo(f'标签数: {len(tags)}')
    click.echo(f'过期条目: {len(expired_entries)}')
    click.echo(f'待复审条目: {len(review_entries)}')
    click.echo(f'历史访问记录: {len(history)}')

    unassigned = [e for e in review_entries if not e.reviewer]
    if unassigned:
        click.echo(f'未指定负责人的待复审: {len(unassigned)}')

    if projects:
        click.echo()
        click.echo('项目分布:')
        for proj in projects:
            count = len(store.list_entries(project=proj))
            bar = '█' * min(count // 5, 20)
            click.echo(f'  {proj}: {count} {bar}')

    if by_reviewer:
        reviewer_map = {}
        for entry in all_entries:
            if entry.reviewer:
                if entry.reviewer not in reviewer_map:
                    reviewer_map[entry.reviewer] = {'total': 0, 'expired': 0, 'needs_review': 0}
                reviewer_map[entry.reviewer]['total'] += 1
                if entry.expired:
                    reviewer_map[entry.reviewer]['expired'] += 1
                if entry.needs_review:
                    reviewer_map[entry.reviewer]['needs_review'] += 1

        if reviewer_map:
            click.echo()
            click.echo('按负责人统计:')
            for name, stats in sorted(reviewer_map.items()):
                parts = [f'共 {stats["total"]} 条']
                if stats['expired']:
                    parts.append(f'🚫{stats["expired"]} 过期')
                if stats['needs_review']:
                    parts.append(f'📋{stats["needs_review"]} 待复审')
                click.echo(f'  👤 {name}: {", ".join(parts)}')

    if tags:
        click.echo()
        click.echo('热门标签 (Top 10):')
        tag_counts = [(tag, len(store.list_entries(tags=[tag]))) for tag in tags]
        tag_counts.sort(key=lambda x: x[1], reverse=True)
        for tag, count in tag_counts[:10]:
            click.echo(f'  {tag}: {count}')


def _build_handoff_markdown(entries, title='复审交接清单'):
    """生成交接清单的 Markdown 内容。"""
    lines = []
    lines.append(f'# 🔄 {title}')
    lines.append('')
    lines.append(f'> 生成时间: **{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**')
    lines.append('')

    expired = [e for e in entries if e.expired]
    need_review = [e for e in entries if e.needs_review]
    unassigned = [e for e in need_review if not e.reviewer]

    lines.append('## 📊 概览')
    lines.append('')
    lines.append(f'- 📋 待复审总数: **{len(need_review)}** 条')
    lines.append(f'  - 已指派: **{len(need_review) - len(unassigned)}** 条')
    lines.append(f'  - 未指派: **{len(unassigned)}** 条')
    lines.append(f'- 🚫 已过期: **{len(expired)}** 条')
    lines.append(f'- 📁 涉及项目: **{len(set(e.project for e in entries))}** 个')
    lines.append(f'- 👤 负责人数: **{len(set(e.reviewer for e in entries if e.reviewer))}** 人')
    lines.append('')

    lines.append('## 👥 按负责人交接')
    lines.append('')

    reviewer_map = {}
    for e in need_review:
        r = e.reviewer or '(未指派)'
        if r not in reviewer_map:
            reviewer_map[r] = []
        reviewer_map[r].append(e)

    if not reviewer_map:
        lines.append('暂无待复审条目 ✅')
        lines.append('')

    for reviewer in sorted(reviewer_map.keys()):
        rev_entries = sorted(reviewer_map[reviewer], key=lambda x: x.updated_at)
        rev_expired = [e for e in rev_entries if e.expired]
        reviewer_icon = '👤' if reviewer != '(未指派)' else '⚠️ '
        lines.append(f'### {reviewer_icon} {reviewer} (共 {len(rev_entries)} 条)')
        lines.append('')
        if rev_expired:
            lines.append(f'> ⚠️  其中 **{len(rev_expired)}** 条已过期，需要优先处理')
            lines.append('')
        lines.append('| # | 标题 | 项目 | 状态 | 备注 | 更新时间 | ID |')
        lines.append('|---|------|------|------|------|----------|----|')
        for i, e in enumerate(rev_entries, 1):
            title_link = e.title.replace('|', '\\|')
            badges = []
            if e.expired:
                badges.append('🚫过期')
            badges.append('📋待复审')
            status_md = ' '.join(badges)
            note_md = (e.review_note or '').replace('|', '\\|')
            if len(note_md) > 40:
                note_md = note_md[:40] + '...'
            lines.append(f'| {i} | {title_link} | {e.project} | {status_md} | {note_md or "-"} | {e.updated_at[:10]} | `{e.id[:8]}` |')
        lines.append('')

    if expired:
        lines.append('## 🚫 过期内容清单')
        lines.append('')
        lines.append('| # | 标题 | 项目 | 负责人 | 备注 | 更新时间 |')
        lines.append('|---|------|------|--------|------|----------|')
        for i, e in enumerate(sorted(expired, key=lambda x: x.updated_at), 1):
            title_link = e.title.replace('|', '\\|')
            note_md = (e.review_note or '').replace('|', '\\|')
            if len(note_md) > 40:
                note_md = note_md[:40] + '...'
            lines.append(f'| {i} | {title_link} | {e.project} | {e.reviewer or "-"} | {note_md or "-"} | {e.updated_at[:10]} |')
        lines.append('')

    lines.append('## 📝 交接说明')
    lines.append('')
    lines.append('### 处理优先级建议：')
    lines.append('1. **P0 - 已过期 + 待复审**：内容已失效且需要审核，立即处理')
    lines.append('2. **P1 - 已过期**：内容不再适用，更新或删除')
    lines.append('3. **P2 - 待复审**：检查内容准确性，标记状态')
    lines.append('')
    lines.append('### 常用命令：')
    lines.append('```bash')
    lines.append('kb review list                      # 查看所有待复审')
    lines.append('kb review mark <ID> --review false   # 完成复审，清除待复审标记')
    lines.append('kb review mark <ID> --expired true   # 标记为过期')
    lines.append('kb show <ID>                         # 查看条目的完整内容')
    lines.append('kb review done <ID> -m "结论"         # 完成复审并写结论')
    lines.append('```')
    lines.append('')

    return '\n'.join(lines)


def _build_handoff_json(entries, title='复审交接清单'):
    """生成交接清单的 JSON 内容。"""
    expired = [e for e in entries if e.expired]
    need_review = [e for e in entries if e.needs_review]

    reviewer_map = {}
    for e in need_review:
        r = e.reviewer or '(未指派)'
        if r not in reviewer_map:
            reviewer_map[r] = []
        reviewer_map[r].append(e.to_dict())

    return {
        'title': title,
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_needs_review': len(need_review),
            'assigned': len([e for e in need_review if e.reviewer]),
            'unassigned': len([e for e in need_review if not e.reviewer]),
            'expired_count': len(expired),
            'projects': sorted(set(e.project for e in entries)),
            'reviewers': sorted(set(e.reviewer for e in entries if e.reviewer)),
        },
        'by_reviewer': {k: v for k, v in sorted(reviewer_map.items())},
        'expired_list': [e.to_dict() for e in expired],
    }


@review_cmd.command('handoff')
@click.option('--reviewer', '-r', help='仅导出指定负责人的条目')
@click.option('--project', '-p', help='仅导出指定项目的条目')
@click.option('--format', '-f', 'fmt', type=click.Choice(['markdown', 'json', 'both']),
              default='markdown', help='输出格式')
@click.option('--output', '-o', help='输出目录或文件名（不指定则输出到标准输出）')
@click.option('--all-entries', is_flag=True, help='包含所有状态条目（不只待复审和过期）')
def handoff(reviewer, project, fmt, output, all_entries):
    """生成复审交接清单（按负责人/项目分组，支持 Markdown/JSON）

    \b
    用法：
      kb review handoff                        # 生成全库交接清单
      kb review handoff -r 张开发               # 生成某负责人的清单
      kb review handoff -p database -f json     # 某项目导出JSON
      kb review handoff -o ./handoff -f both    # 同时输出md和json到目录
    """
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    all_db = store.list_entries(project=project)

    if all_entries:
        entries = all_db
    else:
        entries = [e for e in all_db if e.needs_review or e.expired]

    if reviewer:
        entries = [e for e in entries if e.reviewer == reviewer or (reviewer == '(未指派)' and not e.reviewer)]

    if not entries:
        click.echo('没有需要交接的条目 ✅')
        return

    title_parts = ['复审交接清单']
    if project:
        title_parts.append(f'项目: {project}')
    if reviewer:
        title_parts.append(f'负责人: {reviewer}')
    title = ' - '.join(title_parts)

    md_content = _build_handoff_markdown(entries, title=title)
    json_data = _build_handoff_json(entries, title=title)

    if output:
        out_path = Path(output)
        if out_path.suffix in ('.md', '.json'):
            out_path.parent.mkdir(parents=True, exist_ok=True)
            file_path = out_path
            if fmt == 'both':
                base = out_path.stem
                p = out_path.parent
                if out_path.suffix == '.md':
                    md_target = out_path
                    json_target = p / f'{base}.json'
                else:
                    json_target = out_path
                    md_target = p / f'{base}.md'
                with open(md_target, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                with open(json_target, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                click.echo(f'✅ 已生成交接清单:')
                click.echo(f'   Markdown: {md_target}')
                click.echo(f'   JSON:     {json_target}')
            else:
                if out_path.suffix == '.md' and fmt != 'json':
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(md_content)
                    click.echo(f'✅ 已生成交接清单: {file_path}')
                elif out_path.suffix == '.json' and fmt != 'markdown':
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(json_data, f, ensure_ascii=False, indent=2)
                    click.echo(f'✅ 已生成交接清单: {file_path}')
        else:
            out_path.mkdir(parents=True, exist_ok=True)
            md_file = out_path / 'handoff.md'
            json_file = out_path / 'handoff.json'
            generated = []
            if fmt in ('markdown', 'both'):
                with open(md_file, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                generated.append(f'Markdown: {md_file}')
            if fmt in ('json', 'both'):
                with open(json_file, 'w', encoding='utf-8') as f:
                    json.dump(json_data, f, ensure_ascii=False, indent=2)
                generated.append(f'JSON:     {json_file}')
            click.echo(f'✅ 已生成交接清单:')
            for g in generated:
                click.echo(f'   {g}')
    else:
        if fmt in ('markdown', 'both'):
            click.echo(md_content)
        if fmt == 'both':
            click.echo('\n\n' + '=' * 60 + '\n')
        if fmt in ('json', 'both'):
            click.echo(json.dumps(json_data, ensure_ascii=False, indent=2))


@review_cmd.command('claim')
@click.argument('entry_id')
@click.option('--reviewer', '-r', help='负责人（默认为当前用户名）')
@click.option('--note', '-m', default='', help='认领备注')
@click.option('--mark-review', is_flag=True, help='同时标记为待复审')
def claim_entry(entry_id, reviewer, note, mark_review):
    """认领条目（记录负责人，加入历史记录轨迹）

    \b
    用法：
      kb review claim 564d                          # 认领（默认自己）
      kb review claim 564d -r 张开发 -m "我来处理"   # 指派给某人
    """
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entry, err = store.resolve_entry(entry_id)
    if err:
        click.echo(f'错误: {err}', err=True)
        sys.exit(1)

    old_reviewer = entry.reviewer
    if reviewer:
        entry.reviewer = reviewer
    else:
        entry.reviewer = _get_default_reviewer()

    old_review = entry.needs_review
    if mark_review:
        entry.needs_review = True

    action_note = note if note else '认领该条目'
    if old_reviewer:
        action_note = f'{action_note}（从 {old_reviewer} 交接）'

    entry.add_review_record(
        reviewer=entry.reviewer,
        note=f'[CLAIM] {action_note}',
        old_review=old_review,
        new_review=entry.needs_review,
    )

    store.update_entry(entry)

    click.echo(f'✅ 条目已认领: {entry.title} ({entry.id[:8]})')
    click.echo(f'   负责人: 👤 {entry.reviewer}')
    if old_reviewer and old_reviewer != entry.reviewer:
        click.echo(f'   原负责人: {old_reviewer}')
    if mark_review:
        click.echo(f'   已同时标记为待复审')
    if note:
        click.echo(f'   备注: {note}')
    click.echo(f'   查看历史: kb review history {entry.id[:8]}')


@review_cmd.command('done')
@click.argument('entry_id')
@click.option('--note', '-m', required=True, help='复审结论（必填）')
@click.option('--mark-expired', type=click.Choice(['true', 'false']), help='是否标记为过期')
@click.option('--reviewer', '-r', help='复审人（默认为条目的当前负责人）')
def done_entry(entry_id, note, mark_expired, reviewer):
    """完成复审（清除待复审状态，写结论，记录完整轨迹）

    \b
    用法：
      kb review done 564d -m "已对照MySQL 8.0文档核对，参数依然有效"
      kb review done 564d -m "内容已过时，建议删除" --mark-expired true
    """
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entry, err = store.resolve_entry(entry_id)
    if err:
        click.echo(f'错误: {err}', err=True)
        sys.exit(1)

    old_review = entry.needs_review
    old_expired = entry.expired
    final_reviewer = reviewer or entry.reviewer or _get_default_reviewer()

    entry.needs_review = False
    if mark_expired is not None:
        entry.expired = mark_expired == 'true'
    entry.reviewer = final_reviewer
    entry.review_note = note

    entry.add_review_record(
        reviewer=final_reviewer,
        note=f'[DONE] {note}',
        old_review=old_review,
        new_review=entry.needs_review,
        old_expired=old_expired,
        new_expired=entry.expired,
    )

    store.update_entry(entry)

    status = []
    if entry.expired:
        status.append('已过期')
    if not status:
        status.append('正常')

    click.echo(f'✅ 复审完成: {entry.title} ({entry.id[:8]})')
    click.echo(f'   复审人: 👤 {final_reviewer}')
    click.echo(f'   结论: {note}')
    click.echo(f'   当前状态: {", ".join(status)}')
    click.echo(f'   查看完整历史: kb review history {entry.id[:8]}')
