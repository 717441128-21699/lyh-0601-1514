import click
import sys
import re

from ..config import find_kb_root, Config
from ..store import Store


def _parse_query(query_str):
    """解析搜索查询字符串，返回 (must_keywords, exclude_keywords)"""
    parts = re.split(r'\s+', query_str.strip())
    must = []
    exclude = []
    for part in parts:
        if not part:
            continue
        if part.startswith('-') and len(part) > 1:
            exclude.append(part[1:])
        else:
            must.append(part)
    return must, exclude


def _highlight(text, keywords, exclude_keywords=None, max_len=150):
    """高亮文本中的关键词，并返回最相关的片段"""
    if not text:
        return ''
    if not keywords and not exclude_keywords:
        return text[:max_len] + ('...' if len(text) > max_len else '')

    lower_text = text.lower()
    positions = []
    for kw in keywords:
        idx = 0
        while True:
            idx = lower_text.find(kw.lower(), idx)
            if idx == -1:
                break
            positions.append((idx, len(kw)))
            idx += len(kw)

    if not positions:
        return text[:max_len] + ('...' if len(text) > max_len else '')

    positions.sort(key=lambda x: x[0])

    best_start = 0
    best_score = 0
    half_window = max_len // 2

    for pos, _ in positions:
        start = max(0, pos - half_window)
        end = start + max_len
        score = 0
        for p, _ in positions:
            if start <= p < end:
                score += 1
        if score > best_score:
            best_score = score
            best_start = start

    snippet_start = best_start
    snippet_end = min(len(text), best_start + max_len)

    prefix = '...' if snippet_start > 0 else ''
    suffix = '...' if snippet_end < len(text) else ''
    snippet = text[snippet_start:snippet_end]

    for kw in sorted(keywords, key=lambda x: -len(x)):
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        snippet = pattern.sub(click.style(r'\g<0>', fg='yellow', bold=True), snippet)

    return prefix + snippet + suffix


def _search_entries(store, must_keywords, exclude_keywords, project, tags,
                    title_only, body_only, include_expired):
    """执行搜索，返回 (entries, hit_info)"""
    all_entries = store.list_entries(project=project, tags=tags)

    if not include_expired:
        all_entries = [e for e in all_entries if not e.expired]

    results = []

    for entry in all_entries:
        search_text_title = entry.title.lower()
        search_text_content = entry.content.lower()

        if body_only:
            search_text_all = search_text_content
        elif title_only:
            search_text_all = search_text_title
        else:
            search_text_all = search_text_title + ' ' + search_text_content

        hit = True
        for kw in must_keywords:
            if kw.lower() not in search_text_all:
                hit = False
                break

        if not hit:
            continue

        for kw in exclude_keywords:
            if kw.lower() in search_text_all:
                hit = False
                break

        if not hit:
            continue

        title_hits = []
        content_hits = []
        for kw in must_keywords:
            if kw.lower() in search_text_title:
                title_hits.append(kw)
            if kw.lower() in search_text_content:
                content_hits.append(kw)

        results.append((entry, title_hits, content_hits))

    def sort_key(item):
        entry, title_hits, content_hits = item
        score = 0
        score += len(title_hits) * 10
        score += len(content_hits) * 1
        try:
            from datetime import datetime
            updated = datetime.fromisoformat(entry.updated_at)
            score += updated.timestamp() / 1e12
        except:
            pass
        return -score

    results.sort(key=sort_key)
    return results


@click.command('search')
@click.argument('query', required=True)
@click.option('--project', '-p', help='按项目过滤')
@click.option('--tags', '-t', help='按标签过滤，多个用逗号分隔')
@click.option('--limit', '-n', type=int, default=20, help='显示数量限制')
@click.option('--content/--no-content', 'show_content', default=True, help='是否显示内容摘要')
@click.option('--title-only', is_flag=True, help='仅搜索标题')
@click.option('--body-only', is_flag=True, help='仅搜索正文（不包含标题）')
@click.option('--include-expired', is_flag=True, help='包含过期条目')
@click.option('--show-id', is_flag=True, default=True, help='显示短ID，方便复制使用')
@click.option('--no-highlight', is_flag=True, help='关闭命中高亮')
def search_cmd(query, project, tags, limit, show_content, title_only, body_only,
               include_expired, show_id, no_highlight):
    """全文搜索知识条目（支持多关键词、排除词、标题/正文搜索、命中高亮）

    \b
    搜索语法：
      多个关键词（AND）:  kb search "mysql 慢查询"
      包含排除词（NOT）: kb search "redis 缓存 -持久化"
      仅搜标题:           kb search "MySQL" --title-only
      仅搜正文:           kb search "连接池" --body-only
      组合过滤:           kb search "K8s 故障" -p k8s -t 运维
    """
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    tag_list = []
    if tags:
        tag_list = [t.strip() for t in tags.split(',') if t.strip()]

    must_keywords, exclude_keywords = _parse_query(query)

    search_type = '标题' if title_only else ('正文' if body_only else '标题+正文')
    query_desc_parts = []
    if must_keywords:
        query_desc_parts.append(' & '.join(f'"{kw}"' for kw in must_keywords))
    if exclude_keywords:
        query_desc_parts.append('排除 ' + ' & '.join(f'"{kw}"' for kw in exclude_keywords))
    query_desc = ' + '.join(query_desc_parts) if query_desc_parts else '<空>'

    results = _search_entries(
        store=store,
        must_keywords=must_keywords,
        exclude_keywords=exclude_keywords,
        project=project,
        tags=tag_list if tag_list else None,
        title_only=title_only,
        body_only=body_only,
        include_expired=include_expired,
    )

    if not results:
        click.echo(f'在 {search_type} 中未找到匹配: {query_desc}')
        if not include_expired:
            click.echo('提示: 加上 --include-expired 可同时搜索过期条目')
        return

    results = results[:limit]

    click.echo(f'在 {search_type} 中找到 {len(results)} 条匹配 (显示前 {limit} 条):')
    click.echo(f'  查询条件: {query_desc}')
    if project:
        click.echo(f'  项目过滤: {project}')
    if tag_list:
        click.echo(f'  标签过滤: {", ".join(tag_list)}')
    click.echo('-' * 70)

    for i, (entry, title_hits, content_hits) in enumerate(results, 1):
        status = []
        if entry.expired:
            status.append('🚫过期')
        if entry.needs_review:
            status.append('📋待复审')
        status_str = f' [{" ".join(status)}]' if status else ''

        title_display = entry.title
        if not no_highlight and must_keywords:
            title_display = _highlight(entry.title, must_keywords, max_len=80)

        tags_str = f' [{", ".join(entry.tags)}]' if entry.tags else ''

        click.echo(f'{i:2d}. {title_display}{tags_str}{status_str}')

        id_info = f'ID: {entry.id[:8]}' if show_id else ''
        parts = [p for p in [id_info, f'项目: {entry.project}', f'更新: {entry.updated_at[:10]}'] if p]
        click.echo(f'    {" | ".join(parts)}')

        hit_locations = []
        if title_hits:
            hit_locations.append(click.style(f'标题命中: {", ".join(title_hits)}', fg='green'))
        if content_hits:
            hit_locations.append(click.style(f'正文命中: {", ".join(content_hits)}', fg='cyan'))
        if hit_locations:
            click.echo(f'    🔍 {" | ".join(hit_locations)}')

        if show_content and entry.content and content_hits:
            if no_highlight:
                preview = entry.content[:150].replace('\n', ' ')
                if len(entry.content) > 150:
                    preview += '...'
            else:
                preview = _highlight(entry.content, must_keywords, max_len=150)
            click.echo(f'    {preview}')
        click.echo()

    if results and click.confirm('是否查看某个条目的详情?', default=False):
        num = click.prompt('请输入序号', type=int)
        if 1 <= num <= len(results):
            entry = results[num - 1][0]
            store.record_access(entry.id)
            _print_entry_detail(entry)


def _print_entry_detail(entry):
    click.echo('\n' + '=' * 60)
    click.echo(f'标题: {entry.title}')
    click.echo(f'项目: {entry.project}')
    if entry.tags:
        click.echo(f'标签: {", ".join(entry.tags)}')
    if entry.reviewer:
        click.echo(f'负责人: 👤 {entry.reviewer}')
    if entry.review_note:
        click.echo(f'复审备注: 📝 {entry.review_note}')
    status = []
    if entry.expired:
        status.append('过期')
    if entry.needs_review:
        status.append('待复审')
    if status:
        click.echo(f'状态: {", ".join(status)}')
    if entry.ticket_links:
        click.echo('工单链接:')
        for link in entry.ticket_links:
            click.echo(f'  - {link}')
    if entry.links:
        click.echo('参考链接:')
        for link in entry.links:
            click.echo(f'  - {link}')
    click.echo('-' * 60)
    click.echo(entry.content)
    click.echo('=' * 60)


@click.command('recent')
@click.option('--limit', '-n', type=int, default=10, help='显示数量限制')
@click.option('--show-id', is_flag=True, default=True, help='显示短ID')
def recent_cmd(limit, show_id):
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
            id_part = f'{entry.id[:8]} | ' if show_id else ''
            click.echo(f'{i:2d}. {entry.title}')
            click.echo(f'    {id_part}项目: {entry.project} | 时间: {item["accessed_at"][:19]}')
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
@click.option('--sort', type=click.Choice(['name', 'count']), default='count', help='排序方式')
def tags_cmd(project, sort):
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

    tag_counts = []
    for tag in all_tags:
        count = len([e for e in store.list_entries(tags=[tag]) if not project or e.project == project])
        if count > 0:
            tag_counts.append((tag, count))

    if sort == 'count':
        tag_counts.sort(key=lambda x: -x[1])
    else:
        tag_counts.sort(key=lambda x: x[0].lower())

    click.echo(f'共 {len(tag_counts)} 个标签:')
    for tag, count in tag_counts:
        bar = '█' * min(count, 30)
        click.echo(f'  {tag:<15} {count:3d} {bar}')


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
        entries = store.list_entries(project=proj)
        count = len(entries)
        expired = len([e for e in entries if e.expired])
        review = len([e for e in entries if e.needs_review])
        parts = [f'{count} 条']
        if expired:
            parts.append(f'🚫{expired} 过期')
        if review:
            parts.append(f'📋{review} 待复审')
        bar = '█' * min(count, 30)
        click.echo(f'  {proj:<15} {", ".join(parts)} {bar}')
