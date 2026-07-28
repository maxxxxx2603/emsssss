#!/usr/bin/env python3
# Fix indentation properly

with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with 'web_app = Flask'
start_fix = None
for i, line in enumerate(lines):
    if 'web_app = Flask' in line and 'if __name__' in '\n'.join(lines[max(0,i-5):i]):
        start_fix = i + 1
        break

if start_fix is None:
    print("Could not find target")
    exit(1)

print(f"Starting fix from line {start_fix}")

# Process lines - remove 8 spaces (2 levels) and add back 4 (1 level)
fixed_lines = lines[:start_fix]

for i in range(start_fix, len(lines)):
    line = lines[i]
    # Count leading spaces
    stripped = line.lstrip()
    if not stripped or stripped.startswith('#'):
        fixed_lines.append(line)
    else:
        spaces = len(line) - len(stripped)
        # We want to remove 4 spaces (one indent level) for the "else:" block
        if spaces >= 8:
            # Remove 4 spaces
            fixed_lines.append(' ' * (spaces - 4) + stripped)
        else:
            fixed_lines.append(line)

with open('main.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("✓ Fixed")
