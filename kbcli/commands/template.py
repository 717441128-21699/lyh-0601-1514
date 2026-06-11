import click
import sys
import json
import re
from pathlib import Path
from datetime import datetime

from ..config import find_kb_root, Config
from ..store import Store


PLACEHOLDER_PATTERN = re.compile(r'\{([^{}]*?)\}')


def _detect_placeholders(text: str):
    """从模板字符串中检测占位符 {name}，支持中英文参数名。"""
    if not text:
        return []
    raw = PLACEHOLDER_PATTERN.findall(text)
    valid = []
    for name in raw:
        # 过滤掉含特殊字符的（避免误匹配 Markdown 复杂语法）
        if any(c in name for c in ' {}[]()"\'|`'):
            continue
        if not name.strip():
            continue
        if name not in valid:
            valid.append(name)
    return sorted(valid)


def _fill_template(text: str, values: dict) -> str:
    """用 values 填充模板中的 {key} 占位符。"""
    if not text:
        return text
    for k, v in values.items():
        if v is not None:
            text = text.replace('{' + k + '}', str(v))
    return text


def _prompt_for_params(param_specs, overrides):
    """交互式提示用户输入参数值。"""
    values = dict(overrides)
    for spec in param_specs:
        name = spec['name']
        if name in values and values[name] is not None:
            continue
        prompt = spec.get('prompt', name)
        optional = spec.get('optional', False)
        default = spec.get('default', '')
        if optional:
            user_val = click.prompt(f'{prompt} (可选，回车跳过)', default=default, show_default=False)
        else:
            user_val = click.prompt(f'{prompt}', default=default if default else '')
        values[name] = user_val if user_val else default
    return values


def _build_search_from_template(template, param_values, store):
    """根据模板和参数值构造搜索上下文。"""
    kwargs_tpl = template.get('search_kwargs_template', {})

    # 填充 must/exclude 关键词模板
    must_keywords = []
    for kw_tpl in kwargs_tpl.get('must_keywords', []):
        filled = _fill_template(kw_tpl, param_values).strip()
        if filled:
            must_keywords.append(filled)
    # 支持 query_template 中包含空格的复合关键词（作为整体）
    query_tpl = template.get('query_template')
    if query_tpl:
        filled_query = _fill_template(query_tpl, param_values)
        parts = re.split(r'\s+', filled_query.strip())
        for p in parts:
            if not p:
                continue
            if p.startswith('-') and len(p) > 1:
                # 排除词单独处理，稍后收集
                continue
            if p not in must_keywords:
                must_keywords.append(p)

    exclude_keywords = []
    for kw_tpl in kwargs_tpl.get('exclude_keywords', []):
        filled = _fill_template(kw_tpl, param_values).strip()
        if filled:
            exclude_keywords.append(filled)
    if query_tpl:
        filled_query = _fill_template(query_tpl, param_values)
        parts = re.split(r'\s+', filled_query.strip())
        for p in parts:
            if p.startswith('-') and len(p) > 1:
                exclude_kw = p[1:]
                if exclude_kw and exclude_kw not in exclude_keywords:
                    exclude_keywords.append(exclude_kw)

    project = _fill_template(kwargs_tpl.get('project', ''), param_values) or None
    tags_template = kwargs_tpl.get('tags_template')
    tags = None
    if tags_template:
        filled_tags = _fill_template(tags_template, param_values)
        if filled_tags:
            tags = [t.strip() for t in filled_tags.split(',') if t.strip()]

    title_only = kwargs_tpl.get('title_only', False)
    body_only = kwargs_tpl.get('body_only', False)
    include_expired = kwargs_tpl.get('include_expired', False)
    reviewer = _fill_template(kwargs_tpl.get('reviewer', ''), param_values) or None

    return {
        'must_keywords': must_keywords,
        'exclude_keywords': exclude_keywords,
        'project': project,
        'tags': tags,
        'title_only': title_only,
        'body_only': body_only,
        'include_expired': include_expired,
        'reviewer': reviewer,
    }


def _run_search_with_ctx(store, search_ctx, show_content=True, highlight=True):
    """在 search.py 中复用搜索逻辑。返回 (entries_with_hits, search_desc)。"""
    from .search import _search_entries, _highlight

    must = search_ctx['must_keywords']
    exclude = search_ctx['exclude_keywords']

    results = _search_entries(
        store=store,
        must_keywords=must,
        exclude_keywords=exclude,
        project=search_ctx['project'],
        tags=search_ctx['tags'],
        title_only=search_ctx['title_only'],
        body_only=search_ctx['body_only'],
        include_expired=search_ctx['include_expired'],
    )

    # reviewer 过滤
    if search_ctx.get('reviewer'):
        results = [r for r in results if r[0].reviewer == search_ctx['reviewer']]

    desc_parts = []
    if must:
        desc_parts.append('包含: ' + ' & '.join(f'"{x}"' for x in must))
    if exclude:
        desc_parts.append('排除: ' + ' & '.join(f'"{x}"' for x in exclude))
    if search_ctx['project']:
        desc_parts.append(f'项目: {search_ctx["project"]}')
    if search_ctx['tags']:
        desc_parts.append(f'标签: {",".join(search_ctx["tags"])}')
    if search_ctx['title_only']:
        desc_parts.append('仅搜标题')
    if search_ctx['body_only']:
        desc_parts.append('仅搜正文')
    if search_ctx['include_expired']:
        desc_parts.append('含过期')
    if search_ctx.get('reviewer'):
        desc_parts.append(f'负责人: {search_ctx["reviewer"]}')
    search_desc = ' | '.join(desc_parts) if desc_parts else '全库条目'

    return results, search_desc


@click.group('template')
def template_cmd():
    """管理 Saved Query 搜索模板（支持参数占位符、结果一键导出排障清单）

    \b
    示例：
      kb template create db-troubleshoot  # 创建搜索模板
      kb template list                    # 列出所有模板
      kb template run db-troubleshoot     # 交互式填参数并执行
      kb template run db-troubleshoot --param project=database --param reviewer=张开发
      kb template export ./team-templates.json
      kb template import ./team-templates.json
    """
    pass


@template_cmd.command('list')
@click.option('--group', '-g', help='按分组显示')
def list_templates(group):
    """列出所有 Saved Query 模板"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    templates = store.load_templates()

    if not templates:
        click.echo('暂无 Saved Query 模板')
        click.echo('使用 `kb template create` 创建第一个模板')
        return

    groups = {}
    for name, data in templates.items():
        g = data.get('group', 'default')
        if group and g != group:
            continue
        if g not in groups:
            groups[g] = []
        groups[g].append((name, data))

    total = sum(len(v) for v in groups.values())
    if group:
        click.echo(f'分组 "{group}" 共 {total} 个模板:')
    else:
        click.echo(f'共 {total} 个 Saved Query 模板 ({len(groups)} 个分组):')
    click.echo('-' * 70)

    for group_name in sorted(groups.keys()):
        items = sorted(groups[group_name], key=lambda x: x[0])
        if not group:
            g_disp = '未分组' if group_name == 'default' else group_name
            click.echo(f'\n📂 {g_disp} ({len(items)} 个):')
            click.echo('  ' + '-' * 68)

        for name, data in items:
            desc = data.get('description', '')
            params = data.get('params', [])
            qt = data.get('query_template', '')
            prefix = '  ' if not group else ''
            click.echo(f'{prefix}🔍 {name}')
            if desc:
                click.echo(f'{prefix}   📝 {desc}')
            if params:
                param_names = ', '.join(
                    '{' + p['name'] + '}' + ('(可选)' if p.get('optional') else '')
                    for p in params
                )
                click.echo(f'{prefix}   📋 参数: {param_names}')
            if qt:
                click.echo(f'{prefix}   💡 查询: {qt}')
            created = data.get('created_at', '')[:10]
            if created:
                click.echo(f'{prefix}   📅 创建于: {created}')
            click.echo()


@template_cmd.command('create')
@click.argument('name')
@click.option('--query', '-q', help='查询模板，支持 {param} 占位符，例: "{关键词} 故障 -临时方案"')
@click.option('--project', '-p', help='项目名模板（支持 {param}）')
@click.option('--tags', '-t', help='标签模板，逗号分隔（支持 {param}）')
@click.option('--reviewer', '-r', help='负责人模板（支持 {param}）')
@click.option('--title-only', is_flag=True, help='仅搜索标题')
@click.option('--body-only', is_flag=True, help='仅搜索正文')
@click.option('--include-expired', is_flag=True, help='包含过期内容')
@click.option('--description', '-d', default='', help='模板描述')
@click.option('--group', '-g', default='default', help='分组名称')
@click.option('--yes', '-y', is_flag=True, help='使用默认占位符配置，不进入交互提问')
def create_template(name, query, project, tags, reviewer, title_only, body_only,
                    include_expired, description, group, yes):
    """交互式创建 Saved Query 模板（或通过选项直接指定，加 -y 跳过确认）"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    if not query and not click.confirm('未提供查询模板，是否进入交互式创建?', default=True):
        click.echo('已取消')
        return

    interactive_mode = not query
    # 交互式模式
    if not query:
        click.echo('\n📋 Saved Query 模板创建向导\n')
        query = click.prompt('1. 查询模板（用 {参数名} 作为占位符）',
                             default='{关键词} 故障',
                             show_default=True)
        project = click.prompt('2. 项目过滤（留空不限制，可用 {project}）',
                               default='', show_default=False) or None
        tags = click.prompt('3. 标签过滤（逗号分隔，留空不限制，可用 {tag}）',
                            default='', show_default=False) or None
        scope = click.prompt('4. 搜索范围: [1]标题+正文  [2]仅标题  [3]仅正文',
                             type=click.Choice(['1', '2', '3']), default='1')
        title_only = scope == '2'
        body_only = scope == '3'
        include_expired = click.confirm('5. 包含过期内容?', default=False)
        reviewer = click.prompt('6. 按负责人过滤（留空不限制，可用 {reviewer}）',
                                default='', show_default=False) or None
        if not description:
            description = click.prompt('7. 模板描述', default=f'模板: {query}', show_default=True)
        if group == 'default' and click.confirm('是否加入自定义分组?', default=False):
            group = click.prompt('分组名称', default='排障', show_default=True)

    # 检测占位符
    all_text = ' '.join(filter(None, [query, project, tags, reviewer]))
    placeholder_names = _detect_placeholders(all_text)

    params = []
    if placeholder_names:
        click.echo(f'\n📋 检测到 {len(placeholder_names)} 个占位符: {", ".join("{"+p+"}" for p in placeholder_names)}')
        # -y 跳过 / 命令行直接创建且无 yes 参数时，默认直接创建
        should_configure = False
        if yes:
            should_configure = False
        elif interactive_mode:
            should_configure = click.confirm('为每个占位符配置提示文字?', default=True)
        else:
            should_configure = False  # 命令行直接创建，不询问占位符

        if should_configure:
            for pname in placeholder_names:
                default_prompt = f'请输入 {pname}'
                prompt = click.prompt(f'  "{"{"+pname+"}"}" 的提示文字', default=default_prompt, show_default=True)
                optional = click.confirm(f'  是否可选?', default=False)
                default_val = ''
                if optional:
                    default_val = click.prompt(f'  默认值（留空则无）', default='', show_default=False)
                params.append({
                    'name': pname,
                    'prompt': prompt,
                    'optional': optional,
                    'default': default_val,
                })
        else:
            for pname in placeholder_names:
                params.append({
                    'name': pname,
                    'prompt': f'请输入 {pname}',
                    'optional': False,
                    'default': '',
                })
    else:
        click.echo('（未检测到占位符参数，此模板将固定查询）')

    template_data = {
        'description': description,
        'group': group,
        'query_template': query or '',
        'params': params,
        'search_kwargs_template': {
            'must_keywords': [],
            'exclude_keywords': [],
            'project': project or '',
            'tags_template': tags or '',
            'reviewer': reviewer or '',
            'title_only': title_only,
            'body_only': body_only,
            'include_expired': include_expired,
        },
    }

    store.save_template(name, template_data)

    g_disp = '未分组' if group == 'default' else group
    click.echo(f'\n✅ Saved Query 模板已保存: {name}')
    click.echo(f'   分组: {g_disp}')
    click.echo(f'   描述: {description or "(无)"}')
    if params:
        click.echo(f'   参数: {", ".join("{"+p["name"]+"}" for p in params)}')
    click.echo(f'   运行: kb template run {name}')
    click.echo(f'   预览: kb template preview {name}')


@template_cmd.command('preview')
@click.argument('name')
def preview_template(name):
    """预览模板结构和参数（不执行）"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    templates = store.load_templates()
    if name not in templates:
        click.echo(f'错误: 模板 "{name}" 不存在', err=True)
        click.echo('使用 `kb template list` 查看可用模板')
        sys.exit(1)

    t = templates[name]
    desc = t.get('description', '')
    group = t.get('group', 'default')
    qt = t.get('query_template', '')
    params = t.get('params', [])
    kt = t.get('search_kwargs_template', {})

    click.echo(f'🔍 模板预览: {name}')
    click.echo(f'   分组: {"未分组" if group == "default" else group}')
    click.echo(f'   描述: {desc or "(无)"}')
    if qt:
        click.echo(f'   查询模板: `{qt}`')

    if params:
        click.echo(f'\n📋 参数定义:')
        for p in params:
            opt = ' (可选)' if p.get('optional') else ''
            dft = f' [默认: {p.get("default", "")}]' if p.get('optional') and p.get('default') else ''
            click.echo(f'   - {"{"+p["name"]+"}"}{opt}: {p.get("prompt", p["name"])}{dft}')
    else:
        click.echo(f'\n📋 无参数（固定查询）')

    click.echo(f'\n⚙️  搜索选项:')
    if kt.get('project'):
        click.echo(f'   项目: {kt["project"]}')
    if kt.get('tags_template'):
        click.echo(f'   标签: {kt["tags_template"]}')
    if kt.get('reviewer'):
        click.echo(f'   负责人: {kt["reviewer"]}')
    if kt.get('title_only'):
        click.echo(f'   范围: 仅标题')
    elif kt.get('body_only'):
        click.echo(f'   范围: 仅正文')
    else:
        click.echo(f'   范围: 标题+正文')
    click.echo(f'   包含过期: {"是" if kt.get("include_expired") else "否"}')
    click.echo()
    click.echo(f'💡 执行命令: kb template run {name}')


@template_cmd.command('run')
@click.argument('name')
@click.option('--param', multiple=True, help='直接提供参数 key=value，可多次使用')
@click.option('--limit', '-n', type=int, default=20, help='结果数量限制')
@click.option('--yes', '-y', is_flag=True, help='导出清单时跳过确认')
@click.option('--export-checklist', '-e', 'export_dir',
              help='将结果导出为排障清单 Markdown 到指定目录')
def run_template(name, param, limit, yes, export_dir):
    """运行 Saved Query 模板（交互式填参数，结果可导出排障清单）"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    templates = store.load_templates()
    if name not in templates:
        click.echo(f'错误: 模板 "{name}" 不存在', err=True)
        sys.exit(1)

    template = templates[name]
    param_specs = template.get('params', [])

    # 解析 --param key=value 覆盖
    overrides = {}
    for p in param:
        if '=' in p:
            k, v = p.split('=', 1)
            overrides[k.strip()] = v.strip()

    if len(overrides) < len([x for x in param_specs if not x.get('optional')]):
        click.echo(f'🔍 模板: {name}')
        click.echo(f'📝 {template.get("description", "")}')
        click.echo()

    values = _prompt_for_params(param_specs, overrides)

    search_ctx = _build_search_from_template(template, values, store)
    results, search_desc = _run_search_with_ctx(store, search_ctx)

    click.echo(f'🔍 使用模板 "{name}"')
    click.echo(f'   {search_desc}')
    click.echo(f'   找到 {len(results)} 条结果:')
    click.echo('-' * 70)

    from .search import _highlight
    results = results[:limit]
    for i, (entry, title_hits, content_hits) in enumerate(results, 1):
        status = []
        if entry.expired:
            status.append('🚫过期')
        if entry.needs_review:
            status.append('📋待复审')
        status_str = f' [{" ".join(status)}]' if status else ''

        title_display = _highlight(entry.title, search_ctx['must_keywords'], max_len=80)
        tags_str = f' [{", ".join(entry.tags)}]' if entry.tags else ''
        click.echo(f'{i:2d}. {title_display}{tags_str}{status_str}')
        click.echo(f'    ID: {entry.id[:8]} | 项目: {entry.project} | 更新: {entry.updated_at[:10]}')
        if entry.reviewer:
            click.echo(f'    👤 负责人: {entry.reviewer}')
        if entry.review_note:
            note_preview = entry.review_note[:40] + '...' if len(entry.review_note) > 40 else entry.review_note
            click.echo(f'    📝 备注: {note_preview}')
        click.echo()

    if export_dir and results:
        _write_checklist_markdown(results, name, search_desc, values, export_dir)
    elif results and not export_dir:
        if yes or click.confirm('是否将结果导出为排障清单 Markdown?', default=False):
            default_dir = f'./checklist-{name}-{datetime.now().strftime("%Y%m%d-%H%M%S")}'
            out_dir = click.prompt('输出目录', default=default_dir, show_default=True)
            _write_checklist_markdown(results, name, search_desc, values, out_dir)


@template_cmd.command('remove')
@click.argument('name')
def remove_template(name):
    """删除 Saved Query 模板"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    if store.delete_template(name):
        click.echo(f'已删除模板: {name}')
    else:
        click.echo(f'模板不存在: {name}')


@template_cmd.command('export')
@click.argument('output_file', default='./kb-templates.json')
@click.option('--group', '-g', help='仅导出指定分组')
def export_templates(output_file, group):
    """导出 Saved Query 模板到文件（团队分享）"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    all_templates = store.load_templates()
    if not all_templates:
        click.echo('没有可导出的模板')
        return

    exported = {}
    for name, data in all_templates.items():
        if group and data.get('group', 'default') != group:
            continue
        exported[name] = {
            'description': data.get('description', ''),
            'group': data.get('group', 'default'),
            'query_template': data.get('query_template', ''),
            'params': data.get('params', []),
            'search_kwargs_template': data.get('search_kwargs_template', {}),
        }

    if not exported:
        click.echo(f'分组 "{group}" 没有模板')
        return

    data = {
        'version': '1.0',
        'exported_at': datetime.now().isoformat(),
        'count': len(exported),
        'group_filter': group,
        'templates': exported,
    }

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    groups = sorted(set(d.get('group', 'default') for d in exported.values()))
    click.echo(f'✅ 已导出 {len(exported)} 个模板到 {output_file}')
    if len(groups) > 1 or (len(groups) == 1 and groups[0] != 'default'):
        click.echo(f'   涉及分组: {", ".join(groups)}')


@template_cmd.command('import')
@click.argument('input_file')
@click.option('--yes', '-y', is_flag=True, help='跳过预览确认')
@click.option('--overwrite/--no-overwrite', default=False, help='覆盖同名模板')
@click.option('--prefix', default='', help='导入的模板名称前缀，避免冲突')
@click.option('--group', '-g', help='重新指定导入后的分组')
def import_templates(input_file, yes, overwrite, prefix, group):
    """从文件导入 Saved Query 模板（预览新增/覆盖）"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    input_path = Path(input_file)
    if not input_path.exists():
        click.echo(f'错误: 文件不存在: {input_file}', err=True)
        sys.exit(1)

    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        click.echo(f'错误: JSON 格式无效: {e}', err=True)
        sys.exit(1)

    imported = data.get('templates', {})
    if not imported:
        click.echo('文件中没有模板')
        return

    existing = store.load_templates()

    to_add = {}
    to_overwrite = {}
    conflicts = []

    for tname, tdata in imported.items():
        new_name = prefix + tname
        if group:
            tdata = dict(tdata)
            tdata['group'] = group
        if new_name in existing:
            if overwrite:
                to_overwrite[new_name] = tdata
            else:
                conflicts.append((new_name, tname))
        else:
            to_add[new_name] = tdata

    click.echo('📋 导入预览:')
    click.echo('-' * 70)

    if to_add:
        click.echo(f'\n✅ 新增 ({len(to_add)} 个):')
        for n, t in sorted(to_add.items()):
            desc = t.get('description', '')
            g = t.get('group', 'default')
            g_disp = '未分组' if g == 'default' else g
            qt = t.get('query_template', '')[:50]
            click.echo(f'   🔍 {n}  [{g_disp}]')
            if desc:
                click.echo(f'      📝 {desc}')
            if qt:
                click.echo(f'      💡 {qt}')

    if to_overwrite:
        click.echo(f'\n⚠️  覆盖 ({len(to_overwrite)} 个):')
        for n, t in sorted(to_overwrite.items()):
            old_desc = existing[n].get('description', '(无)')
            new_desc = t.get('description', '(无)')
            click.echo(f'   🔍 {n}')
            click.echo(f'      旧描述: {old_desc}')
            click.echo(f'      新描述: {new_desc}')

    if conflicts and not overwrite:
        click.echo(f'\n❌ 跳过 ({len(conflicts)} 个冲突，使用 --overwrite 覆盖或 --prefix 重命名):')
        for new_name, orig_name in conflicts:
            t = imported[orig_name]
            click.echo(f'   - {new_name} (已存在)')

    total = len(to_add) + len(to_overwrite)
    if total == 0:
        click.echo('\n没有可导入的模板')
        return

    click.echo(f'\n合计: 新增 {len(to_add)}, 覆盖 {len(to_overwrite)}')

    if not yes:
        if not click.confirm('是否确认导入?', default=True):
            click.echo('已取消导入')
            return

    merge_data = {}
    merge_data.update(to_add)
    merge_data.update(to_overwrite)

    if overwrite and conflicts:
        for new_name, orig_name in conflicts:
            merge_data[new_name] = imported[orig_name]

    for n, td in merge_data.items():
        store.save_template(n, td)

    actual_total = len(merge_data)
    click.echo(f'\n✅ 导入完成: 共 {actual_total} 个模板')
    if to_add:
        click.echo(f'   新增: {len(to_add)} 个')
    if to_overwrite:
        click.echo(f'   覆盖: {len(to_overwrite)} 个')
    click.echo(f'   查看: kb template list')


def _write_checklist_markdown(results, template_name, search_desc, param_values, output_dir):
    """将搜索结果导出为 Markdown 排障清单。"""
    entries = [r[0] for r in results]
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    checklist_path = out_path / 'checklist.md'

    lines = []
    lines.append(f'# 🛠️  排障清单 - {template_name}')
    lines.append('')
    lines.append(f'> 生成时间: **{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}**')
    lines.append(f'> 使用模板: **{template_name}**')
    lines.append('')

    if param_values:
        lines.append('## 📥 执行参数')
        lines.append('')
        for k, v in param_values.items():
            lines.append(f'- **{k}**: {v if v else "(空)"}')
        lines.append('')

    lines.append('## 🎯 搜索条件')
    lines.append('')
    lines.append(f'- {search_desc}')
    lines.append(f'- 命中数: **{len(entries)}**')
    lines.append('')

    # 统计
    expired = [e for e in entries if e.expired]
    need_review = [e for e in entries if e.needs_review]
    projects = sorted(set(e.project for e in entries))
    reviewers = sorted(set(e.reviewer for e in entries if e.reviewer))
    lines.append('## 📊 结果概览')
    lines.append('')
    lines.append(f'- 📁 项目数: {len(projects)} ({", ".join(projects)})')
    if reviewers:
        lines.append(f'- 👤 负责人: {len(reviewers)} 人 ({", ".join(reviewers)})')
    lines.append(f'- 🚫 已过期: {len(expired)} 条')
    lines.append(f'- 📋 待复审: {len(need_review)} 条')
    lines.append('')

    # 逐项清单
    lines.append('## 📋 逐项排障清单')
    lines.append('')
    lines.append('| # | 标题 | 项目 | 状态 | 负责人 | 备注 | 进度 |')
    lines.append('|---|------|------|------|--------|------|------|')
    for i, e in enumerate(entries, 1):
        badges = []
        if e.expired:
            badges.append('🚫过期')
        if e.needs_review:
            badges.append('📋待复审')
        status_md = ' '.join(badges) if badges else '✅'
        link_title = e.title.replace('|', '\\|')
        reviewer = e.reviewer or '-'
        note = (e.review_note or '').replace('|', '\\|')
        if len(note) > 30:
            note = note[:30] + '...'
        note = note or '-'
        lines.append(f'| {i} | {link_title} | {e.project} | {status_md} | {reviewer} | {note} | ☐ |')
    lines.append('')

    # 每个条目详情区
    lines.append('## 📝 条目详情')
    lines.append('')
    for i, e in enumerate(entries, 1):
        badges = []
        if e.expired:
            badges.append('🚫过期')
        if e.needs_review:
            badges.append('📋待复审')
        status = ' '.join(badges) if badges else '✅'
        lines.append(f'### {i}. {e.title}')
        lines.append('')
        lines.append(f'- **状态**: {status}')
        lines.append(f'- **项目**: {e.project}')
        if e.tags:
            lines.append(f'- **标签**: {", ".join(e.tags)}')
        lines.append(f'- **更新时间**: {e.updated_at[:19]}')
        if e.last_accessed:
            lines.append(f'- **最近访问**: {e.last_accessed[:19]} (共 {e.access_count} 次)')
        if e.reviewer:
            lines.append(f'- **负责人**: 👤 {e.reviewer}')
        if e.review_note:
            lines.append(f'- **备注**: 📝 {e.review_note}')
        if e.ticket_links:
            lines.append(f'- **工单**:')
            for tl in e.ticket_links:
                lines.append(f'  - [{tl}]({tl})')
        if e.links:
            lines.append(f'- **参考链接**:')
            for rl in e.links:
                lines.append(f'  - {rl}')
        lines.append(f'- **ID**: `{e.id[:8]}`')
        lines.append('')
        lines.append('#### 📌 处理记录')
        lines.append('')
        lines.append('| 步骤 | 操作人 | 时间 | 备注 |')
        lines.append('|------|--------|------|------|')
        lines.append('|      |        |      |      |')
        lines.append('')
        lines.append('---')
        lines.append('')

    lines.append('## 📎 后续步骤')
    lines.append('')
    lines.append('- [ ] 逐项核对条目内容准确性')
    lines.append('- [ ] 处理待复审标记，使用 `kb review done <ID> -m "结论"` 完成')
    lines.append('- [ ] 更新过期条目或标记删除')
    lines.append('- [ ] 在条目基础上新增解决经验 `kb add`')
    lines.append('')

    with open(checklist_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))

    click.echo(f'\n✅ 排障清单已导出: {checklist_path}')
    click.echo(f'   条目数: {len(entries)}')
