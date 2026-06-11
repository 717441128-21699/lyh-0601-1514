import click
import sys
import shlex
import json
from pathlib import Path
from datetime import datetime

from ..config import find_kb_root, Config
from ..store import Store


@click.group('shortcut')
def shortcut_cmd():
    """管理快捷命令（支持分组、导出/导入、预览确认）"""
    pass


@shortcut_cmd.command('list')
@click.option('--group', '-g', help='按分组显示')
def list_shortcuts(group):
    """列出所有快捷命令（支持按分组筛选）"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    shortcuts = store.load_shortcuts()

    if not shortcuts:
        click.echo('暂无快捷命令')
        click.echo('使用 `kb shortcut add` 或 `kb shortcut save-search` 添加')
        return

    groups = {}
    for name, data in shortcuts.items():
        g = data.get('group', 'default')
        if group and g != group:
            continue
        if g not in groups:
            groups[g] = []
        groups[g].append((name, data))

    total = sum(len(v) for v in groups.values())
    if group:
        click.echo(f'分组 "{group}" 共 {total} 个快捷命令:')
    else:
        click.echo(f'共 {total} 个快捷命令 ({len(groups)} 个分组):')
    click.echo('-' * 70)

    for group_name in sorted(groups.keys()):
        items = sorted(groups[group_name], key=lambda x: x[0])
        if not group:
            group_display = '未分组' if group_name == 'default' else group_name
            click.echo(f'\n📂 {group_display} ({len(items)} 个):')
            click.echo('  ' + '-' * 68)

        for name, data in items:
            desc = data.get('description', '')
            if 'args' in data and data['args']:
                args = data['args']
                cmd_display = ' '.join(_quote_arg(a) for a in args)
            else:
                cmd_display = data.get('command', '')

            prefix = '  ' if not group else ''
            click.echo(f'{prefix}🚀 {name}')
            if desc:
                click.echo(f'{prefix}   📝 {desc}')
            click.echo(f'{prefix}   ▶️  kb {cmd_display}')
            created = data.get('created_at', '')[:10]
            if created:
                click.echo(f'{prefix}   📅 创建于: {created}')
            click.echo()


@shortcut_cmd.command('add')
@click.argument('name')
@click.argument('command_parts', nargs=-1, required=True)
@click.option('--description', '-d', default='', help='快捷命令描述')
@click.option('--group', '-g', default='default', help='分组名称')
def add_shortcut(name, command_parts, description, group):
    """添加快捷命令（支持带空格和中文的复杂参数）

    用法示例：
      kb shortcut add find-k8s search "k8s 故障" --tags 运维
      kb shortcut add db-tips search --project database MySQL 优化
      kb shortcut add -g 排障 find-k8s search "Pod 启动失败"
    """
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    args_list = list(command_parts)
    cmd_str = ' '.join(_quote_arg(a) for a in args_list)

    store.save_shortcut(name, cmd_str, description, args=args_list, group=group)

    group_display = '未分组' if group == 'default' else group
    click.echo(f'✅ 快捷命令已添加: {name}')
    click.echo(f'   分组: {group_display}')
    click.echo(f'   描述: {description or "(无)"}')
    click.echo(f'   命令: kb {cmd_str}')
    click.echo(f'   预览: kb shortcut preview {name}')
    click.echo(f'   运行: kb shortcut run {name}')


@shortcut_cmd.command('remove')
@click.argument('name')
def remove_shortcut(name):
    """删除快捷命令"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    if store.delete_shortcut(name):
        click.echo(f'已删除快捷命令: {name}')
    else:
        click.echo(f'未找到快捷命令: {name}')


@shortcut_cmd.command('preview')
@click.argument('name')
@click.argument('extra_args', nargs=-1)
def preview_shortcut(name, extra_args):
    """预览快捷命令将要执行的内容（不实际执行）"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    shortcuts = store.load_shortcuts()
    if name not in shortcuts:
        click.echo(f'错误: 未找到快捷命令 {name}', err=True)
        click.echo('使用 `kb shortcut list` 查看所有快捷命令')
        sys.exit(1)

    shortcut = shortcuts[name]
    args_list, desc, cmd_str = _expand_shortcut(shortcut, list(extra_args))
    full_cmd = ['kb'] + args_list
    group = shortcut.get('group', 'default')
    group_display = '未分组' if group == 'default' else group

    click.echo(f'📋 快捷命令预览: {name}')
    click.echo(f'   分组: {group_display}')
    click.echo(f'   描述: {desc or "(无)"}')
    click.echo()
    click.echo(f'🔧 执行参数:')
    for i, a in enumerate(args_list, 1):
        click.echo(f'   [{i}] {a}')
    click.echo()
    click.echo(f'▶️  完整命令:')
    click.echo(f'   {" ".join(_quote_arg(a) for a in full_cmd)}')
    click.echo()
    click.echo(f'💡 使用 kb shortcut run {name} 实际执行')


@shortcut_cmd.command('run')
@click.argument('name')
@click.argument('extra_args', nargs=-1)
@click.option('--yes', '-y', is_flag=True, help='跳过确认直接执行')
def run_shortcut(name, extra_args, yes):
    """运行快捷命令（支持追加额外参数，执行前可预览确认）"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    shortcuts = store.load_shortcuts()
    if name not in shortcuts:
        click.echo(f'错误: 未找到快捷命令 "{name}"', err=True)
        click.echo('使用 `kb shortcut list` 查看所有快捷命令')
        sys.exit(1)

    shortcut = shortcuts[name]
    args_list, desc, cmd_str = _expand_shortcut(shortcut, list(extra_args))
    full_cmd = ['kb'] + args_list

    click.echo(f'🚀 快捷命令: {name}')
    if desc:
        click.echo(f'📝 {desc}')
    click.echo(f'▶️  执行: {" ".join(_quote_arg(a) for a in full_cmd)}')
    click.echo('-' * 60)

    if not yes:
        if not click.confirm('是否继续执行?', default=True):
            click.echo('已取消执行')
            return

    from .. import cli as cli_module
    try:
        cli_module.cli(args_list, standalone_mode=True)
    except SystemExit as e:
        sys.exit(e.code)
    except Exception as e:
        click.echo(f'执行错误: {e}', err=True)
        sys.exit(1)


@shortcut_cmd.command('save-search')
@click.argument('name')
@click.argument('query')
@click.option('--project', '-p', help='按项目过滤')
@click.option('--tags', '-t', help='按标签过滤')
@click.option('--title-only', is_flag=True, help='仅搜索标题')
@click.option('--body-only', is_flag=True, help='仅搜索正文')
@click.option('--include-expired', is_flag=True, help='包含过期条目')
@click.option('--content/--no-content', default=True, help='搜索时显示内容摘要')
@click.option('--description', '-d', default='', help='描述')
@click.option('--group', '-g', default='default', help='分组名称')
def save_search(name, query, project, tags, title_only, body_only, include_expired,
                content, description, group):
    """保存常用搜索为快捷命令（自动处理空格和中文关键词）

    用法：
      kb shortcut save-search find-trouble "故障排查指南" --tags 运维
      kb shortcut save-search k8s-pod "Pod 启动失败" -p k8s -g 排障
    """
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    args_list = ['search', query]
    if project:
        args_list.extend(['--project', project])
    if tags:
        args_list.extend(['--tags', tags])
    if title_only:
        args_list.append('--title-only')
    if body_only:
        args_list.append('--body-only')
    if include_expired:
        args_list.append('--include-expired')
    if not content:
        args_list.append('--no-content')

    cmd_str = ' '.join(_quote_arg(a) for a in args_list)

    if not description:
        desc_parts = [f'搜索: {query}']
        if project:
            desc_parts.append(f'项目: {project}')
        if tags:
            desc_parts.append(f'标签: {tags}')
        scope = []
        if title_only:
            scope.append('仅标题')
        if body_only:
            scope.append('仅正文')
        if scope:
            desc_parts.append('范围: ' + ','.join(scope))
        description = ' | '.join(desc_parts)

    store.save_shortcut(name, cmd_str, description, args=args_list, group=group)

    group_display = '未分组' if group == 'default' else group
    click.echo(f'✅ 搜索快捷命令已保存: {name}')
    click.echo(f'   分组: {group_display}')
    click.echo(f'   描述: {description}')
    click.echo(f'   命令: kb {cmd_str}')
    click.echo(f'   预览: kb shortcut preview {name}')
    click.echo(f'   执行: kb shortcut run {name}')


@shortcut_cmd.command('export')
@click.argument('output_file', default='./kb-shortcuts.json')
@click.option('--group', '-g', help='仅导出指定分组')
@click.option('--all-groups', is_flag=True, help='导出所有分组（默认）')
@click.option('--include-meta/--no-meta', default=True, help='包含创建时间等元信息')
def export_shortcuts(output_file, group, all_groups, include_meta):
    """导出快捷命令到文件（用于团队分享）

    用法：
      kb shortcut export ./troubleshooting.json -g 排障
      kb shortcut export ./all-shortcuts.json
    """
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    all_shortcuts = store.load_shortcuts()

    if not all_shortcuts:
        click.echo('没有可导出的快捷命令')
        return

    exported = {}
    for name, data in all_shortcuts.items():
        if group and data.get('group', 'default') != group:
            continue
        if include_meta:
            exported[name] = data
        else:
            exported[name] = {
                'command': data.get('command', ''),
                'description': data.get('description', ''),
                'args': data.get('args'),
                'group': data.get('group', 'default'),
            }

    if not exported:
        if group:
            click.echo(f'分组 "{group}" 没有快捷命令')
        else:
            click.echo('没有可导出的快捷命令')
        return

    data = {
        'version': '1.0',
        'exported_at': datetime.now().isoformat(),
        'count': len(exported),
        'group_filter': group,
        'shortcuts': exported,
    }

    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    groups = set(d.get('group', 'default') for d in exported.values())
    click.echo(f'✅ 已导出 {len(exported)} 个快捷命令到 {output_file}')
    if len(groups) > 1:
        click.echo(f'   涉及分组: {", ".join(sorted(groups))}')


@shortcut_cmd.command('import')
@click.argument('input_file')
@click.option('--yes', '-y', is_flag=True, help='跳过预览确认直接导入')
@click.option('--overwrite/--no-overwrite', default=False, help='覆盖已存在的同名快捷命令')
@click.option('--prefix', default='', help='为导入的快捷命令名称添加前缀，避免冲突')
@click.option('--group', '-g', help='重新指定导入后的分组，不指定则使用原分组')
def import_shortcuts(input_file, yes, overwrite, prefix, group):
    """从文件导入快捷命令（支持预览、覆盖、分组重映射）

    用法：
      kb shortcut import ./team-shortcuts.json
      kb shortcut import ./team-shortcuts.json --prefix team-
      kb shortcut import ./team-shortcuts.json -g 分享
    """
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
        click.echo(f'错误: JSON 文件格式无效: {e}', err=True)
        sys.exit(1)

    imported = data.get('shortcuts', {})
    if not imported:
        click.echo('文件中没有快捷命令')
        return

    existing = store.load_shortcuts()

    to_add = {}
    to_overwrite = {}
    conflicts = []

    for name, sc_data in imported.items():
        new_name = prefix + name

        if group:
            sc_data = dict(sc_data)
            sc_data['group'] = group

        if new_name in existing:
            if overwrite:
                to_overwrite[new_name] = sc_data
            else:
                conflicts.append((new_name, name))
        else:
            to_add[new_name] = sc_data

    if conflicts and not overwrite:
        click.echo(f'⚠️  有 {len(conflicts)} 个快捷命令名称冲突:')
        for new_name, orig_name in conflicts:
            sc = imported[orig_name]
            click.echo(f'   - {new_name}（已存在，使用 --overwrite 覆盖或 --prefix 重命名）')
            click.echo(f'     描述: {sc.get("description", "(无)")}')
        click.echo()

    if not to_add and not to_overwrite:
        click.echo('没有需要导入的快捷命令')
        return

    click.echo('📋 导入预览:')
    click.echo('-' * 70)

    if to_add:
        click.echo(f'\n✅ 新增 ({len(to_add)} 个):')
        for name, sc in sorted(to_add.items()):
            desc = sc.get('description', '')
            grp = sc.get('group', 'default')
            grp_disp = '未分组' if grp == 'default' else grp
            cmd = sc.get('command', '')[:60]
            click.echo(f'   🚀 {name}  [分组: {grp_disp}]')
            if desc:
                click.echo(f'      📝 {desc}')
            click.echo(f'      ▶️  kb {cmd}')

    if to_overwrite:
        click.echo(f'\n⚠️  覆盖 ({len(to_overwrite)} 个):')
        for name, sc in sorted(to_overwrite.items()):
            desc = sc.get('description', '')
            grp = sc.get('group', 'default')
            grp_disp = '未分组' if grp == 'default' else grp
            old_desc = existing[name].get('description', '(无)')
            click.echo(f'   🚀 {name}  [分组: {grp_disp}]')
            click.echo(f'      旧描述: {old_desc}')
            click.echo(f'      新描述: {desc or "(无)"}')

    click.echo(f'\n合计: 新增 {len(to_add)} 个, 覆盖 {len(to_overwrite)} 个')
    if conflicts and not overwrite:
        click.echo(f'      跳过 {len(conflicts)} 个冲突 (使用 --overwrite 覆盖)')
    click.echo()

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

    if merge_data:
        if overwrite:
            store.save_shortcuts(merge_data, overwrite=False)
        else:
            for name, sc in merge_data.items():
                store.save_shortcut(
                    name=name,
                    command=sc.get('command', ''),
                    description=sc.get('description', ''),
                    args=sc.get('args'),
                    group=sc.get('group', 'default'),
                )

    total_imported = len(merge_data)
    if overwrite:
        total_imported += len(conflicts)

    click.echo(f'\n✅ 导入完成: 共 {total_imported} 个快捷命令')
    if to_add:
        click.echo(f'   新增: {len(to_add)} 个')
    if to_overwrite:
        click.echo(f'   覆盖: {len(to_overwrite)} 个')
    if overwrite and conflicts:
        click.echo(f'   覆盖冲突: {len(conflicts)} 个')
    click.echo(f'   使用 kb shortcut list 查看全部')


def _quote_arg(arg: str) -> str:
    """根据参数内容决定是否需要 shell 引号。"""
    if any(c in arg for c in ' \t\n"\''):
        return '"' + arg.replace('"', '\\"') + '"'
    return arg


def _expand_shortcut(shortcut_data, extra_args):
    """从快捷命令数据中展开参数列表。

    优先使用保存的 args（列表形式，支持空格和中文）；
    若没有 args，回退到解析旧格式的 command 字符串。
    """
    desc = shortcut_data.get('description', '')

    if 'args' in shortcut_data and shortcut_data['args']:
        args_list = list(shortcut_data['args'])
        cmd_str = shortcut_data.get('command') or ' '.join(
            _quote_arg(a) for a in args_list
        )
    else:
        cmd_str = shortcut_data.get('command', '')
        try:
            args_list = shlex.split(cmd_str)
        except ValueError:
            args_list = cmd_str.split()

    if extra_args:
        args_list = args_list + extra_args

    return args_list, desc, cmd_str
