import click
import sys

from . import __version__
from .commands import (
    init_cmd,
    add_cmd, list_cmd, show_cmd, edit_cmd, delete_cmd,
    search_cmd, recent_cmd, tags_cmd, projects_cmd,
    link_cmd,
    review_cmd,
    export_cmd,
    shortcut_cmd,
)


@click.group()
@click.version_option(version=__version__, prog_name='kb')
def cli():
    """团队知识库命令行工具

    用于研发和运维团队在终端快速查找内部经验。
    """
    pass


cli.add_command(init_cmd)
cli.add_command(add_cmd)
cli.add_command(list_cmd)
cli.add_command(show_cmd)
cli.add_command(edit_cmd)
cli.add_command(delete_cmd)
cli.add_command(search_cmd)
cli.add_command(recent_cmd)
cli.add_command(tags_cmd)
cli.add_command(projects_cmd)
cli.add_command(link_cmd)
cli.add_command(review_cmd)
cli.add_command(export_cmd)
cli.add_command(shortcut_cmd)


def main():
    try:
        cli()
    except KeyboardInterrupt:
        click.echo('\n已取消')
        sys.exit(0)


if __name__ == '__main__':
    main()
