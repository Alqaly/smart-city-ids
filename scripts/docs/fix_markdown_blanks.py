#!/usr/bin/env python3
import sys
from pathlib import Path
import re

def fix_file(p: Path):
    text = p.read_text(encoding='utf-8')
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # ensure blank line before heading
        if re.match(r'^(#{1,6})\s', line):
            if out and out[-1].strip() != '':
                out.append('')
            out.append(line)
            i += 1
            continue
        # ensure fenced code blocks surrounded by blank lines
        if line.strip().startswith('```'):
            # ensure blank before
            if out and out[-1].strip() != '':
                out.append('')
            out.append(line)
            i += 1
            # copy until closing fence
            while i < len(lines):
                out.append(lines[i])
                if lines[i].strip().startswith('```'):
                    i += 1
                    break
                i += 1
            # ensure blank after
            if i < len(lines) and lines[i].strip() != '':
                out.append('')
            continue
        out.append(line)
        i += 1
    new_text = '\n'.join(out) + '\n'
    if new_text != text:
        p.write_text(new_text, encoding='utf-8')
        return True
    return False

root = Path('docs')
changed = []
for p in sorted(root.rglob('*.md')):
    if fix_file(p):
        changed.append(str(p))

if changed:
    print('Fixed files:')
    for c in changed:
        print(' -', c)
    sys.exit(0)
else:
    print('No changes made')
    sys.exit(0)
