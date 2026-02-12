#!/usr/bin/env python3
"""
Comprehensive markdown fixer for markdownlint issues:
- MD022/MD032: Add blank lines around headings and lists
- MD040: Add language tags to fenced code blocks
- MD034: Convert bare URLs to markdown links
- MD036: Replace emphasis-as-heading with proper headings
- MD026: Remove trailing punctuation from headings
- MD029: Fix ordered list numbering
- MD012: Remove multiple consecutive blank lines
"""
import os
import re
from pathlib import Path

def fix_markdown_file(file_path):
    """Apply all markdown fixes to a file."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    
    # Fix 1: Add language tags to bare code fences
    content = re.sub(r'^```\s*$', '```bash', content, flags=re.MULTILINE)
    
    # Fix 2: Remove multiple consecutive blank lines (MD012)
    content = re.sub(r'\n\n\n+', '\n\n', content)
    
    # Fix 3: Fix emphasis-as-heading (MD036) - convert *text* or **text** to ### text
    # Look for lines that are JUST emphasis (no other content)
    content = re.sub(r'^(\s*)\*\*([^*]+)\*\*\s*$', r'\1### \2', content, flags=re.MULTILINE)
    content = re.sub(r'^(\s*)\*([^*]+)\*\s*$', r'\1## \2', content, flags=re.MULTILINE)
    
    # Fix 4: Remove trailing punctuation from headings (MD026)
    content = re.sub(r'^(#{1,6}\s+.+):\s*$', r'\1', content, flags=re.MULTILINE)
    
    # Fix 5: Fix ordered list numbering (MD029) - convert to consistent 1, 2, 3... format
    def fix_ordered_lists(text):
        lines = text.split('\n')
        result = []
        list_counter = 0
        in_list = False
        
        for line in lines:
            # Check if line is an ordered list item
            match = re.match(r'^(\s*)(\d+)\.\s+(.+)$', line)
            if match:
                indent, num, content_part = match.groups()
                if not in_list or list_counter == 0:
                    in_list = True
                    list_counter = 1
                else:
                    list_counter += 1
                result.append(f'{indent}{list_counter}. {content_part}')
            elif line.strip() == '':
                result.append(line)
                list_counter = 0  # Reset on blank line
                in_list = False
            else:
                result.append(line)
                list_counter = 0
                in_list = False
        
        return '\n'.join(result)
    
    content = fix_ordered_lists(content)
    
    # Fix 6: Convert bare URLs to markdown links (MD034)
    # Match https:// or http:// URLs not already in []()
    # Avoid matching URLs already in links [text](url) or <url>
    bare_url_pattern = r'(?<!\[)(?<!\()(?<!\<)(https?://[^\s\)>\]]+)(?!\))'
    
    def replace_bare_url(match):
        url = match.group(1)
        # Clean up trailing punctuation that's not part of URL
        if url.endswith(')'):
            url = url[:-1]
        return f'<{url}>'
    
    content = re.sub(bare_url_pattern, replace_bare_url, content)
    
    # Fix 7: Ensure blank lines around headings and lists (MD022/MD032)
    lines = content.split('\n')
    result_lines = []
    
    for i, line in enumerate(lines):
        result_lines.append(line)
        
        # Check if current line is a heading
        if re.match(r'^#{1,6}\s+', line):
            # Add blank line after heading if next line isn't blank or EOF
            if i + 1 < len(lines) and lines[i + 1].strip() != '':
                result_lines.append('')
        
        # Check if current line is a list item
        if re.match(r'^\s*[-*+]\s+', line) or re.match(r'^\s*\d+\.\s+', line):
            # Add blank line after list if next line isn't blank/list and not EOF
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line != '' and not re.match(r'^([-*+]|\d+\.)\s+', next_line):
                    # Check we're not already adding blank line
                    if result_lines[-1].strip() != '':
                        result_lines.append('')
    
    content = '\n'.join(result_lines)
    
    # Clean up any doubled blank lines that may have been added
    content = re.sub(r'\n\n\n+', '\n\n', content)
    
    if content != original:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    """Fix all markdown files in docs/"""
    docs_dir = Path('/home/kali/smart-city-ids/docs')
    fixed_files = []
    
    for md_file in sorted(docs_dir.glob('*.md')):
        if fix_markdown_file(str(md_file)):
            fixed_files.append(md_file.name)
    
    if fixed_files:
        print(f"✅ Fixed {len(fixed_files)} files:")
        for f in fixed_files:
            print(f"  - {f}")
    else:
        print("No files needed fixes")

if __name__ == '__main__':
    main()
