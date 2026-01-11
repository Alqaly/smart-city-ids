#!/usr/bin/env python3
"""Final markdown fixes for remaining issues."""
import os
import re
from pathlib import Path

def fix_file(file_path):
    """Apply final fixes."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Fix MD012: Remove multiple consecutive blank lines
    content = re.sub(r'\n\n\n+', '\n\n', content)
    
    # Fix MD047: Ensure single trailing newline
    content = content.rstrip('\n') + '\n'
    
    # Fix MD031/MD032: Add blank lines around code fences and lists
    lines = content.split('\n')
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        result.append(line)
        
        # After code fence opening, ensure blank line before content
        if line.strip().startswith('```'):
            i += 1
            # Skip language tag line if it exists
            if i < len(lines) and not lines[i].strip().startswith('```'):
                if i + 1 < len(lines) and lines[i + 1].strip() != '' and not lines[i + 1].strip().startswith('```'):
                    result.append(lines[i])
                    result.append('')
                    i += 1
                    continue
        
        # After list item, add blank before non-list content
        if re.match(r'^\s*[-*+]\s+', line) or re.match(r'^\s*\d+\.\s+', line):
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # If next is not list/heading/blank, add blank
                if next_line and not re.match(r'^([-*+]|\d+\.|\#)', next_line):
                    result.append('')
        
        i += 1
    
    content = '\n'.join(result)
    
    # Fix MD001: Heading increment - if file starts with h3, ensure h1/h2 first
    lines = content.split('\n')
    first_heading_idx = -1
    first_heading_level = 0
    
    for i, line in enumerate(lines):
        match = re.match(r'^(#+)\s+', line)
        if match:
            first_heading_idx = i
            first_heading_level = len(match.group(1))
            break
    
    if first_heading_idx >= 0 and first_heading_level > 1:
        # This file starts with h3+ when it should start with h1 or h2
        # Add missing h1 at the beginning
        lines.insert(0, '')
        lines.insert(0, '# ' + lines[2].lstrip('#').strip())
        lines.insert(1, '')
        content = '\n'.join(lines)
    
    if content != original:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    docs_dir = Path('/home/aka/smart-city-ids/docs')
    fixed = []
    
    for md_file in sorted(docs_dir.glob('*.md')):
        if fix_file(str(md_file)):
            fixed.append(md_file.name)
    
    if fixed:
        print(f"✅ Final fixes applied to {len(fixed)} files:")
        for f in fixed:
            print(f"  - {f}")
    else:
        print("No additional fixes needed")

if __name__ == '__main__':
    main()
