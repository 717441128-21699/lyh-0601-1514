import click
import sys
import re
import urllib.request
import urllib.error

from ..config import find_kb_root, Config
from ..store import Store


URL_PATTERN = re.compile(
    r'https?://[^\s<>"\')\]]+'
)


def extract_url(link_text):
    """从链接文本中提取真正的 URL。

    支持格式：
      - 纯 URL: "https://example.com/foo"
      - 带描述: "文档标题: https://example.com/foo"
      - Markdown 链接: "[标题](https://example.com/foo)"
    """
    match = URL_PATTERN.search(link_text)
    if match:
        return match.group(0)
    return link_text.strip()


def extract_link_label(link_text):
    """提取链接的显示名称（去除 URL 部分的描述）。"""
    url = extract_url(link_text)
    if url == link_text:
        return link_text
    label = link_text.replace(url, '').strip(' :：-')
    return label or url


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

    entry, err = store.resolve_entry(entry_id)
    if err:
        click.echo(f'错误: {err}', err=True)
        sys.exit(1)

    if ticket_url not in entry.ticket_links:
        entry.ticket_links.append(ticket_url)
        store.update_entry(entry)
        click.echo(f'已添加工单链接: {ticket_url}')
        click.echo(f'  所属条目: {entry.title} ({entry.id})')
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

    entry, err = store.resolve_entry(entry_id)
    if err:
        click.echo(f'错误: {err}', err=True)
        sys.exit(1)

    link_text = f'{description}: {url}' if description else url
    if url not in entry.links and link_text not in entry.links:
        entry.links.append(link_text)
        store.update_entry(entry)
        click.echo(f'已添加参考链接: {link_text}')
        click.echo(f'  所属条目: {entry.title} ({entry.id})')
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

    entry, err = store.resolve_entry(entry_id)
    if err:
        click.echo(f'错误: {err}', err=True)
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

    entry, err = store.resolve_entry(entry_id)
    if err:
        click.echo(f'错误: {err}', err=True)
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
            url = extract_url(link)
            label = extract_link_label(link)
            if url != label:
                click.echo(f'  {i}. {label}')
                click.echo(f'     → {url}')
            else:
                click.echo(f'  {i}. {link}')
    else:
        click.echo('暂无参考链接')


@link_cmd.command('check')
@click.option('--entry', help='只检查指定条目')
@click.option('--timeout', type=int, default=5, help='超时时间(秒)')
@click.option('--show-all/--show-broken-only', default=False, help='显示所有链接检查结果')
def check_links(entry, timeout, show_all):
    """检查断链（支持带描述的参考链接和工单链接）"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    click.echo('正在检查链接...')

    if entry:
        entry_obj, err = store.resolve_entry(entry)
        if err:
            click.echo(f'错误: {err}', err=True)
            sys.exit(1)
        entries_to_check = [entry_obj]
    else:
        entries_to_check = store.list_entries()

    all_results = []
    broken_count = 0
    total_count = 0

    for entry_obj in entries_to_check:
        all_links_with_type = []
        for tl in entry_obj.ticket_links:
            all_links_with_type.append(('工单', tl))
        for rl in entry_obj.links:
            all_links_with_type.append(('参考', rl))

        for link_type, link_text in all_links_with_type:
            total_count += 1
            url = extract_url(link_text)
            label = extract_link_label(link_text)

            result = {
                'entry_id': entry_obj.id,
                'entry_title': entry_obj.title,
                'link_type': link_type,
                'link_text': link_text,
                'link_label': label,
                'url': url,
            }

            if not (url.startswith('http://') or url.startswith('https://')):
                result['status'] = 'SKIP'
                result['message'] = '非 HTTP(S) 链接，已跳过'
                all_results.append(result)
                continue

            try:
                req = urllib.request.Request(url, method='HEAD', headers={
                    'User-Agent': 'Mozilla/5.0 (kbcli link checker)'
                })
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status >= 400:
                        result['status'] = 'FAIL'
                        result['http_status'] = resp.status
                        result['message'] = f'HTTP {resp.status}'
                        broken_count += 1
                    else:
                        result['status'] = 'OK'
                        result['http_status'] = resp.status
                        result['message'] = f'HTTP {resp.status} 正常'
            except urllib.error.HTTPError as e:
                result['status'] = 'FAIL'
                result['http_status'] = e.code
                result['message'] = f'HTTP {e.code}'
                broken_count += 1
            except Exception as e:
                result['status'] = 'FAIL'
                result['message'] = str(e)
                broken_count += 1

            all_results.append(result)

    click.echo()
    click.echo('=' * 70)
    click.echo(f'链接检查完成: 共 {total_count} 条，失败 {broken_count} 条')
    click.echo('=' * 70)
    click.echo()

    results_to_show = all_results if show_all else [r for r in all_results if r['status'] != 'OK']
    if not results_to_show:
        click.echo('所有链接检查通过!')
        return

    for i, result in enumerate(results_to_show, 1):
        status_icon = {'OK': '✅', 'FAIL': '❌', 'SKIP': '⚠️'}.get(result['status'], '?')
        click.echo(f'{status_icon} [{result["status"]}] #{i}')
        click.echo(f'   条目: {result["entry_title"]} ({result["entry_id"][:8]})')
        click.echo(f'   类型: {result["link_type"]}链接')

        if result['link_label'] != result['url']:
            click.echo(f'   描述: {result["link_label"]}')

        click.echo(f'   URL:  {result["url"]}')
        click.echo(f'   结果: {result["message"]}')
        click.echo()

    if broken_count > 0:
        click.echo(f'提示: 有 {broken_count} 条链接异常，请检查上述条目并更新链接。')
    else:
        click.echo('所有链接均正常!')


def _check_entry_links(entry, timeout):
    """保留旧接口，供其他模块调用。"""
    broken = []
    all_links = entry.links + entry.ticket_links
    for link in all_links:
        url = extract_url(link)
        try:
            if url.startswith('http://') or url.startswith('https://'):
                req = urllib.request.Request(url, method='HEAD')
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
