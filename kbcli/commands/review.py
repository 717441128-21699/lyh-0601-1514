import click
import sys
from datetime import datetime, timedelta
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
