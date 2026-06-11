from setuptools import setup, find_packages

setup(
    name='kbcli',
    version='0.1.0',
    description='团队知识库命令行工具',
    packages=find_packages(),
    install_requires=[
        'click>=8.0.0',
        'pyyaml>=6.0',
        'python-dateutil>=2.8',
    ],
    entry_points={
        'console_scripts': [
            'kb=kbcli.cli:cli',
        ],
    },
    python_requires='>=3.8',
)
