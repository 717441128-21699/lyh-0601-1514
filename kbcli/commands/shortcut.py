import click
import sys
import subprocess

from ..config import find_kb_root, Config
from ..store import Store


@click.group('shortcut')
def shortcut_cmd():
    """管理快捷命令"""
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
        cmd = data.get('command', '')
        click.echo(f'  {name}:')
        if desc:
            click.echo(f'    描述: {desc}')
        click.echo(f'    命令: kb {cmd}')


@shortcut_cmd.command('add')
@click.argument('name')
@click.argument('command')
@click.option('--description', '-d', default='', help='快捷命令描述')
def add_shortcut(name, command, description):
    """添加快捷命令"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    if command.startswith('kb '):
        command = command[3:]

    store.save_shortcut(name, command, description)
    click.echo(f'快捷命令已添加: {name}')
    click.echo(f'  命令: kb {command}')


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
        click.echo(f'快捷命令已删除: {name}')
    else:
        click.echo(f'未找到快捷命令: {name}')


@shortcut_cmd.command('run')
@click.argument('name')
@click.argument('args', nargs=-1)
def run_shortcut(name, args):
    """运行快捷命令"""
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
    cmd_parts = shortcut['command'].split()

    full_cmd = ['kb'] + cmd_parts + list(args)

    click.echo(f'运行快捷命令: {name}')
    click.echo(f'  完整命令: {" ".join(full_cmd)}')
    click.echo('-' * 60)

    import shlex
    import os
    os.execvp('kb', full_cmd)


@shortcut_cmd.command('save-search')
@click.argument('name')
@click.argument('keyword')
@click.option('--project', '-p', help='按项目过滤')
@click.option('--tags', '-t', help='按标签过滤')
@click.option('--description', '-d', default='', help='描述')
def save_search(name, keyword, project, tags, description):
    """保存常用搜索为快捷命令"""
    kb_root = find_kb_root()
    if not kb_root:
        click.echo('错误: 未找到知识库，请先运行 kb init', err=True)
        sys.exit(1)

    config = Config(kb_root)
    store = Store(config)

    cmd_parts = ['search', keyword]
    if project:
        cmd_parts.extend(['--project', project])
    if tags:
        cmd_parts.extend(['--tags', tags])

    command = ' '.join(cmd_parts)
    if not description:
        description = f'搜索: {keyword}'

    store.save_shortcut(name, command, description)
    click.echo(f'搜索快捷命令已保存: {name}')
    click.echo(f'  命令: kb {command}')
