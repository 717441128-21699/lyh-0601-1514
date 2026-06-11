import click
import sys

from ..config import find_kb_root, Config
from ..store import Store


@click.group('link')
def link_cmd():
    """管理知识条目的相关链接"""
    pass


@link_cmd.command('add-ticket')
@click.argument('entry_id')
@click.argument('ticket_url')
@click.option('--type', '-t', default='ticket', help='链接类型')
def add_ticket(entry_id, ticket_url, type):
    """添加工单链接到条目"""
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

    if ticket_url not in entry.ticket_links:
        entry.ticket_links.append(ticket_url)
        store.update_entry(entry)
        click.echo(f'已添加工单链接: {ticket_url}')
    else:
        click.echo('该工单链接已存在')


@link_cmd.command('add-link')
@click.argument('entry_id')
@click.argument('url')
@click.option('--description', '-d', default='', help='链接描述')
def add_link(entry_id, url, description):
    """添加参考链接到条目"""
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

    link_text = f'{description}: {url}' if description else url
    if url not in entry.links and link_text not in entry.links:
        entry.links.append(link_text)
        store.update_entry(entry)
        click.echo(f'已添加参考链接: {link_text}')
    else:
        click.echo('该参考链接已存在')


@link_cmd.command('remove')
@click.argument('entry_id')
@click.argument('url')
@click.option('--ticket', is_flag=True, help='删除的是工单链接')
def remove_link(entry_id, url, ticket):
    """删除条目链接"""
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

    if ticket:
        if url in entry.ticket_links:
            entry.ticket_links.remove(url)
            store.update_entry(entry)
            click.echo(f'已删除工单链接: {url}')
        else:
            click.echo('未找到该工单链接')
    else:
        found = False
        for i, link in enumerate(entry.links):
            if url in link:
                del entry.links[i]
                found = True
                break
        if found:
            store.update_entry(entry)
            click.echo(f'已删除参考链接: {url}')
        else:
            click.echo('未找到该参考链接')


@link_cmd.command('list')
@click.argument('entry_id')
def list_links(entry_id):
    """列出条目的所有链接"""
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

    click.echo(f'条目: {entry.title} ({entry.id})')
    click.echo()

    if entry.ticket_links:
        click.echo('工单链接:')
        for i, link in enumerate(entry.ticket_links, 1):
            click.echo(f'  {i}. {link}')
    else:
        click.echo('暂无工单链接')

    click.echo()

    if entry.links:
        click.echo('参考链接:')
        for i, link in enumerate(entry.links, 1):
            click.echo(f'  {i}. {link}')
    else:
        click.echo('暂无参考链接')


@link_cmd.command('check')
@click.option('--entry', help='只检查指定条目')
@click.option('--timeout', type=int, default=5, help='超时时间(秒)')
def check_links(entry, timeout):
    """检查断链"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    click.echo('正在检查链接...')

    if entry:
        entry_obj = store.get_entry(entry)
        if not entry_obj:
            click.echo(f'错误: 未找到条目 {entry}', err=True)
            sys.exit(1)
        broken = _check_entry_links(entry_obj, timeout)
    else:
        broken = store.check_broken_links()

    if not broken:
        click.echo('所有链接都正常!')
        return

    click.echo(f'\n发现 {len(broken)} 个失效链接:')
    click.echo('-' * 60)
    for item in broken:
        click.echo(f'条目: {item["entry_title"]} ({item["entry_id"][:8]})')
        click.echo(f'链接: {item["link"]}')
        if 'status' in item:
            click.echo(f'状态: HTTP {item["status"]}')
        if 'error' in item:
            click.echo(f'错误: {item["error"]}')
        click.echo()


def _check_entry_links(entry, timeout):
    import urllib.request
    import urllib.error
    broken = []
    all_links = entry.links + entry.ticket_links
    for link in all_links:
        try:
            if link.startswith('http://') or link.startswith('https://'):
                req = urllib.request.Request(link, method='HEAD')
                with urllib.request.urlopen(req, timeout=timeout) as resp:
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
