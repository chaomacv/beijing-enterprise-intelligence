"""Check the Git index before publishing. Never prints matched credential values."""
import re
import subprocess
from pathlib import PurePosixPath

allowed = {'.env.example', '.gitattributes', '.gitignore', '.github', 'README.md', 'pyproject.toml', 'src', 'tests', 'docs', 'scripts'}
paths = subprocess.check_output(['git', 'ls-files', '-z']).decode().split('\0')
credential = re.compile(rb'(?:AIza[0-9A-Za-z_-]{30,}|gh[pousr]_[0-9A-Za-z]{20,}|-----BEGIN (?:RSA |OPENSSH )?PRIVATE KEY-----)')
errors = []
for name in filter(None, paths):
    if PurePosixPath(name).parts[0] not in allowed:
        errors.append((name, 'unexpected top-level path'))
        continue
    if PurePosixPath(name).suffix.lower() in {'.csv', '.xlsx', '.xls', '.rdf', '.sqlite', '.db', '.pem', '.key'}:
        errors.append((name, 'private/data file type'))
    content = subprocess.check_output(['git', 'show', ':' + name])
    if len(content) > 1024 * 1024: errors.append((name, 'large file needs explicit source review'))
    if credential.search(content): errors.append((name, 'possible credential'))
if errors:
    for name, reason in errors: print(name, reason)
    raise SystemExit(1)
print('Git index check passed: source, documentation and tests only.')
