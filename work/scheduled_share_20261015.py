"""Run the existing privacy audit including newly added project files."""
from pathlib import Path

path = Path(__file__).with_name('audit_github_share.py')
source = path.read_text(encoding='utf-8')
old = "git('ls-files', '-z')"
new = "git('ls-files', '--cached', '--others', '--exclude-standard', '-z')"
assert source.count(old) == 1
exec(compile(source.replace(old, new), str(path), 'exec'),
     {'__file__': str(path), '__name__': '__main__'})
