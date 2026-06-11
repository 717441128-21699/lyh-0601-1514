import click
import sys
import shlex

from ..config import find_kb_root, Config
from ..store import Store


@click.group('shortcut')
def shortcut_cmd():
    """管理快捷命令（支持保存带空格、中文、过滤条件的复杂查询）"""
    pass


@shortcut_cmd.command('list')
def list_shortcuts():
    """列出所有快捷命令"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    shortcuts = store.load_shortcuts()

    if not shortcuts:
        click.echo('暂无快捷命令')
        return

    click.echo(f'共 {len(shortcuts)} 个快捷命令:')
    click.echo('-' * 60)
    for name, data in sorted(shortcuts.items()):
        desc = data.get('description', '')
        if 'args' in data and data['args']:
            args = data['args']
            cmd_display = ' '.join(_quote_arg(a) for a in args)
        else:
            cmd_display = data.get('command', '')

        click.echo(f'  🚀 {name}')
        if desc:
            click.echo(f'     📝 {desc}')
        click.echo(f'     ▶️  kb {cmd_display}')
        click.echo()


@shortcut_cmd.command('add')
@click.argument('name')
@click.argument('command_parts', nargs=-1, required=True)
@click.option('--description', '-d', default='', help='快捷命令描述')
def add_shortcut(name, command_parts, description):
    """添加快捷命令（支持带空格和中文的复杂参数）

    用法示例：
      kb shortcut add find-k8s search "k8s 故障" --tags 运维
      kb shortcut add db-tips search --project database MySQL 优化
    """
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    args_list = list(command_parts)
    cmd_str = ' '.join(_quote_arg(a) for a in args_list)

    store.save_shortcut(name, cmd_str, description, args=args_list)

    click.echo(f'✅ 快捷命令已添加: {name}')
    click.echo(f'   描述: {description or "(无)"}')
    click.echo(f'   命令: kb {cmd_str}')
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

    click.echo(f'📋 快捷命令预览: {name}')
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
@click.argument('keyword')
@click.option('--project', '-p', help='按项目过滤')
@click.option('--tags', '-t', help='按标签过滤')
@click.option('--content/--no-content', default=False, help='搜索时显示内容摘要')
@click.option('--description', '-d', default='', help='描述')
def save_search(name, keyword, project, tags, content, description):
    """保存常用搜索为快捷命令（自动处理空格和中文关键词）

    用法：
      kb shortcut save-search find-trouble "故障排查指南" --tags 运维,故障排查
      kb shortcut save-search k8s-pod "Pod 启动失败" -p k8s
    """
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    args_list = ['search', keyword]
    if project:
        args_list.extend(['--project', project])
    if tags:
        args_list.extend(['--tags', tags])
    if content:
        args_list.append('--content')

    cmd_str = ' '.join(_quote_arg(a) for a in args_list)

    if not description:
        desc_parts = [f'搜索: {keyword}']
        if project:
            desc_parts.append(f'项目: {project}')
        if tags:
            desc_parts.append(f'标签: {tags}')
        description = ' | '.join(desc_parts)

    store.save_shortcut(name, cmd_str, description, args=args_list)

    click.echo(f'✅ 搜索快捷命令已保存: {name}')
    click.echo(f'   描述: {description}')
    click.echo(f'   命令: kb {cmd_str}')
    click.echo(f'   预览: kb shortcut preview {name}')
    click.echo(f'   执行: kb shortcut run {name}')


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
