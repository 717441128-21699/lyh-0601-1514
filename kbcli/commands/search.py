import click
import sys

from ..config import find_kb_root, Config
from ..store import Store


@click.command('search')
@click.argument('keyword', required=True)
@click.option('--project', '-p', help='按项目过滤')
@click.option('--tags', '-t', help='按标签过滤，多个用逗号分隔')
@click.option('--limit', '-n', type=int, default=20, help='显示数量限制')
@click.option('--content/--no-content', default=False, help='是否显示内容摘要')
def search_cmd(keyword, project, tags, limit, content):
    """全文搜索知识条目"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]

    entries = store.search_entries(
        keyword=keyword,
        project=project,
        tags=tag_list if tag_list else None,
    )

    if not entries:
        click.echo(f'没有找到包含 "{keyword}" 的条目')
        return

    entries = entries[:limit]

    click.echo(f'找到 {len(entries)} 条匹配结果 (显示前 {limit} 条):')
    click.echo('-' * 60)
    for i, entry in enumerate(entries, 1):
        tags_str = f' [{", ".join(entry.tags)}]' if entry.tags else ''
        click.echo(f'{i:2d}. {entry.title}{tags_str}')
        click.echo(f'    ID: {entry.id[:8]} | 项目: {entry.project} | 更新: {entry.updated_at[:10]}')
        if content and entry.content:
            preview = entry.content[:100].replace('\n', ' ')
            if len(entry.content) > 100:
                preview += '...'
            click.echo(f'    {preview}')
        click.echo()

    if entries and click.confirm('是否查看某个条目的详情?', default=False):
        num = click.prompt('请输入序号', type=int)
        if 1 <= num <= len(entries):
            entry = entries[num - 1]
            store.record_access(entry.id)
            _print_entry_detail(entry)


def _print_entry_detail(entry):
    click.echo('\n' + '=' * 60)
    click.echo(f'标题: {entry.title}')
    click.echo(f'项目: {entry.project}')
    if entry.tags:
        click.echo(f'标签: {", ".join(entry.tags)}')
    if entry.ticket_links:
        click.echo('工单链接:')
        for link in entry.ticket_links:
            click.echo(f'  - {link}')
    click.echo('-' * 60)
    click.echo(entry.content)
    click.echo('=' * 60)


@click.command('recent')
@click.option('--limit', '-n', type=int, default=10, help='显示数量限制')
def recent_cmd(limit):
    """查看最近访问的条目"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    history = store.load_history()
    if not history:
        click.echo('暂无访问记录')
        return

    history = history[:limit]

    click.echo(f'最近访问 (最近 {limit} 条):')
    click.echo('-' * 60)
    for i, item in enumerate(history, 1):
        entry = store.get_entry(item['entry_id'])
        if entry:
            click.echo(f'{i:2d}. {entry.title}')
            click.echo(f'    ID: {entry.id[:8]} | 项目: {entry.project} | 时间: {item["accessed_at"][:19]}')
        else:
            click.echo(f'{i:2d}. [条目已删除] {item["entry_id"]}')
            click.echo(f'    时间: {item["accessed_at"][:19]}')

    if history and click.confirm('是否重新查看某个条目?', default=False):
        num = click.prompt('请输入序号', type=int)
        if 1 <= num <= len(history):
            item = history[num - 1]
            entry = store.get_entry(item['entry_id'])
            if entry:
                store.record_access(entry.id)
                _print_entry_detail(entry)


@click.command('tags')
@click.option('--project', '-p', help='按项目过滤')
def tags_cmd(project):
    """列出所有标签"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    all_tags = store.list_all_tags()
    if not all_tags:
        click.echo('暂无标签')
        return

    click.echo(f'共 {len(all_tags)} 个标签:')
    for tag in all_tags:
        count = len([e for e in store.list_entries(tags=[tag]) if not project or e.project == project])
        click.echo(f'  - {tag} ({count} 条)')


@click.command('projects')
def projects_cmd():
    """列出所有项目"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    projects = store.list_projects()
    if not projects:
        click.echo('暂无项目')
        return

    click.echo(f'共 {len(projects)} 个项目:')
    for proj in projects:
        count = len(store.list_entries(project=proj))
        click.echo(f'  - {proj} ({count} 条)')
