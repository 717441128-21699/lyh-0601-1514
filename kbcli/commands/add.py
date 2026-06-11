import click
import sys
from pathlib import Path

from ..config import find_kb_root, Config
from ..store import Store
from ..models import Entry


@click.command('add')
@click.argument('title', required=False)
@click.option('--project', '-p', default='default', help='所属项目')
@click.option('--tags', '-t', default='', help='标签，多个用逗号分隔')
@click.option('--content', '-c', default='', help='条目内容')
@click.option('--file', '-f', type=click.Path(exists=True), help='从文件读取内容')
@click.option('--ticket', multiple=True, help='关联工单链接，可多次指定')
@click.option('--link', multiple=True, help='关联参考链接，可多次指定')
@click.option('--edit', '-e', is_flag=True, help='使用编辑器编辑内容')
def add_cmd(title, project, tags, content, file, ticket, link, edit):
    """添加知识条目"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    if not title:
        title = click.prompt('请输入标题')

    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]

    if file:
        with open(file, 'r', encoding='utf-8') as f:
            content = f.read()
    elif edit:
        content = click.edit(content or '') or content
    elif not content:
        content = click.edit('') or ''

    ticket_links = list(ticket)
    ref_links = list(link)

    entry = Entry(
        id='',
        title=title,
        content=content,
        project=project,
        tags=tag_list,
        links=ref_links,
        ticket_links=ticket_links,
    )

    entry = store.add_entry(entry)

    click.echo(f'条目已添加:')
    click.echo(f'  ID: {entry.id}')
    click.echo(f'  标题: {entry.title}')
    click.echo(f'  项目: {entry.project}')
    if entry.tags:
        click.echo(f'  标签: {", ".join(entry.tags)}')
    click.echo(f'  创建时间: {entry.created_at}')


@click.command('list')
@click.option('--project', '-p', help='按项目过滤')
@click.option('--tags', '-t', help='按标签过滤，多个用逗号分隔')
@click.option('--expired', is_flag=True, help='只显示过期条目')
@click.option('--review', is_flag=True, help='只显示待复审条目')
@click.option('--limit', '-n', type=int, default=20, help='显示数量限制')
def list_cmd(project, tags, expired, review, limit):
    """列出知识条目"""
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
        expired=True if expired else None,
        needs_review=True if review else None,
    )

    if not entries:
        click.echo('没有找到匹配的条目')
        return

    entries = entries[:limit]

    click.echo(f'共找到 {len(entries)} 条 (显示前 {limit} 条):')
    click.echo('-' * 60)
    for entry in entries:
        status = []
        if entry.expired:
            status.append('过期')
        if entry.needs_review:
            status.append('待复审')
        status_str = f' [{", ".join(status)}]' if status else ''

        tags_str = f' [{", ".join(entry.tags)}]' if entry.tags else ''
        click.echo(f'{entry.id[:8]}  {entry.title}{tags_str}{status_str}')
        click.echo(f'        项目: {entry.project} | 更新: {entry.updated_at[:10]}')


@click.command('show')
@click.argument('entry_id')
def show_cmd(entry_id):
    """查看条目详情"""
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

    store.record_access(entry_id)

    click.echo(f'标题: {entry.title}')
    click.echo(f'ID: {entry.id}')
    click.echo(f'项目: {entry.project}')
    if entry.tags:
        click.echo(f'标签: {", ".join(entry.tags)}')
    click.echo(f'创建: {entry.created_at}')
    click.echo(f'更新: {entry.updated_at}')
    click.echo(f'访问: {entry.access_count} 次')

    status = []
    if entry.expired:
        status.append('过期')
    if entry.needs_review:
        status.append('待复审')
    if status:
        click.echo(f'状态: {", ".join(status)}')

    if entry.ticket_links:
        click.echo('\n工单链接:')
        for link in entry.ticket_links:
            click.echo(f'  - {link}')

    if entry.links:
        click.echo('\n参考链接:')
        for link in entry.links:
            click.echo(f'  - {link}')

    click.echo('\n' + '=' * 60)
    click.echo(entry.content)


@click.command('edit')
@click.argument('entry_id')
@click.option('--title', help='修改标题')
@click.option('--project', '-p', help='修改项目')
@click.option('--tags', '-t', help='修改标签，多个用逗号分隔')
@click.option('--content', '-c', help='修改内容')
@click.option('--append', '-a', is_flag=True, help='追加内容而非替换')
@click.option('--expired', type=click.Choice(['true', 'false']), help='标记过期状态')
@click.option('--review', type=click.Choice(['true', 'false']), help='标记待复审状态')
def edit_cmd(entry_id, title, project, tags, content, append, expired, review):
    """编辑知识条目"""
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

    if title:
        entry.title = title
    if project:
        entry.project = project
    if tags is not None:
        entry.tags = [t.strip() for t in tags.split(',') if t.strip()]
    if content:
        if append:
            entry.content += '\n\n' + content
        else:
            entry.content = content

    if expired is not None:
        entry.expired = expired == 'true'
    if review is not None:
        entry.needs_review = review == 'true'

    store.update_entry(entry)
    click.echo(f'条目已更新: {entry.id}')


@click.command('delete')
@click.argument('entry_id')
@click.option('--yes', '-y', is_flag=True, help='跳过确认')
def delete_cmd(entry_id, yes):
    """删除知识条目"""
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

    if not yes:
        click.echo(f'将删除条目: {entry.title} ({entry.id})')
        if not click.confirm('确定要删除吗?', default=False):
            click.echo('已取消')
            return

    store.delete_entry(entry_id)
    click.echo(f'条目已删除: {entry_id}')
