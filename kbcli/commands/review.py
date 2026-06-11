import click
import sys
from datetime import datetime, timedelta

from ..config import find_kb_root, Config
from ..store import Store


@click.group('review')
def review_cmd():
    """内容复审管理"""
    pass


@review_cmd.command('list')
@click.option('--project', '-p', help='按项目过滤')
@click.option('--limit', '-n', type=int, default=20, help='显示数量限制')
def list_review(project, limit):
    """列出待复审的条目"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entries = store.list_entries(project=project, needs_review=True)

    if not entries:
        click.echo('没有待复审的条目')
        return

    entries = entries[:limit]

    click.echo(f'共 {len(entries)} 条待复审 (显示前 {limit} 条):')
    click.echo('-' * 60)
    for entry in entries:
        click.echo(f'{entry.id[:8]}  {entry.title}')
        click.echo(f'        项目: {entry.project} | 更新: {entry.updated_at[:10]}')
        if entry.tags:
            click.echo(f'        标签: {", ".join(entry.tags)}')


@review_cmd.command('mark')
@click.argument('entry_id')
@click.option('--review', type=click.Choice(['true', 'false']), help='标记待复审状态')
@click.option('--expired', type=click.Choice(['true', 'false']), help='标记过期状态')
def mark_entry(entry_id, review, expired):
    """标记条目状态"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    entry = store.get_entry(entry_id)
    if not entry:
        click.echo(f'错误: 未找到条目 {entry_id}', err=True)
        sys.exit(1)

    if review is not None:
        entry.needs_review = review == 'true'
    if expired is not None:
        entry.expired = expired == 'true'

    store.update_entry(entry)

    status = []
    if entry.needs_review:
        status.append('待复审')
    if entry.expired:
        status.append('过期')
    click.echo(f'条目已标记: {", ".join(status) if status else "无特殊标记"}')


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
    click.echo('-' * 60)
    for entry in entries:
        click.echo(f'{entry.id[:8]}  {entry.title}')
        click.echo(f'        项目: {entry.project} | 更新: {entry.updated_at[:10]}')


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
    click.echo('-' * 60)
    for updated, entry in stale_entries:
        days_old = (datetime.now() - updated).days
        click.echo(f'{entry.id[:8]}  {entry.title}')
        click.echo(f'        项目: {entry.project} | {days_old} 天未更新')


@review_cmd.command('index')
@click.option('--output', '-o', help='输出文件路径，默认输出到标准输出')
@click.option('--project', '-p', help='按项目生成索引')
@click.option('--group-by-tag', is_flag=True, help='按标签分组')
def generate_index(output, project, group_by_tag):
    """生成目录索引"""
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
                lines.append(f'- **{entry.title}**{status_str}{tags_str}')
                lines.append(f'  - ID: `{entry.id}`')
                lines.append(f'  - 更新: {entry.updated_at[:10]}')
            lines.append('')

    content = '\n'.join(lines)

    if output:
        with open(output, 'w', encoding='utf-8') as f:
            f.write(content)
        click.echo(f'目录索引已生成: {output}')
    else:
        click.echo(content)


@review_cmd.command('stats')
def stats():
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
    click.echo('=' * 40)
    click.echo(f'总条目数: {len(all_entries)}')
    click.echo(f'项目数: {len(projects)}')
    click.echo(f'标签数: {len(tags)}')
    click.echo(f'过期条目: {len(expired_entries)}')
    click.echo(f'待复审条目: {len(review_entries)}')
    click.echo(f'历史访问记录: {len(history)}')

    if projects:
        click.echo()
        click.echo('项目分布:')
        for proj in projects:
            count = len(store.list_entries(project=proj))
            bar = '█' * min(count // 5, 20)
            click.echo(f'  {proj}: {count} {bar}')

    if tags:
        click.echo()
        click.echo('热门标签 (Top 10):')
        tag_counts = [(tag, len(store.list_entries(tags=[tag]))) for tag in tags]
        tag_counts.sort(key=lambda x: x[1], reverse=True)
        for tag, count in tag_counts[:10]:
            click.echo(f'  {tag}: {count}')
