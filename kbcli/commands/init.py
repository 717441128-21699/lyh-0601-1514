import click
import os
import json
from pathlib import Path

from ..config import Config, find_kb_root


@click.command('init')
@click.option('--path', '-p', default='.', help='知识库根目录路径，默认为当前目录')
@click.option('--name', '-n', default='team-kb', help='知识库名称')
def init_cmd(path, name):
    """初始化团队知识库"""
    kb_root = Path(path).resolve()
    config = Config(kb_root)

    if config.is_initialized():
        click.echo(f'知识库已存在于: {kb_root}')
        return

    config.kb_dir.mkdir(parents=True, exist_ok=True)
    config.entries_dir.mkdir(parents=True, exist_ok=True)
    config.projects_dir.mkdir(parents=True, exist_ok=True)

    kb_config = {
        'name': name,
        'version': '1.0',
        'created_at': __import__('datetime').datetime.now().isoformat(),
        'default_project': 'default',
    }
    config.save_config(kb_config)

    index = {}
    with open(config.index_path, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)

    with open(config.history_path, 'w', encoding='utf-8') as f:
        json.dump([], f, ensure_ascii=False, indent=2)

    with open(config.shortcuts_path, 'w', encoding='utf-8') as f:
        json.dump({}, f, ensure_ascii=False, indent=2)

    readme_path = kb_root / 'README.md'
    if not readme_path.exists():
        readme_content = f"""# {name}

团队知识库，使用 `kb` 命令行工具管理。

## 快速开始

```bash
# 添加知识条目
kb add "标题" --project 项目名 --tags 标签1,标签2

# 搜索
kb search "关键词"

# 查看所有条目
kb list
```

## 命令说明

- `kb init` - 初始化知识库
- `kb add` - 添加知识条目
- `kb search` - 搜索知识条目
- `kb link` - 管理相关链接
- `kb review` - 内容复审管理
- `kb export` - 导出知识库
- `kb shortcut` - 管理快捷命令
"""
        with open(readme_path, 'w', encoding='utf-8') as f:
            f.write(readme_content)

    click.echo(f'知识库已初始化: {kb_root}')
    click.echo(f'名称: {name}')
