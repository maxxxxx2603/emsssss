#!/usr/bin/env python3
# Fix indentation in main.py after removing the "else:" block

with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with "if __name__ == "__main__":"
start_indent_fix = None
for i, line in enumerate(lines):
    if 'if __name__ == "__main__":' in line:
        start_indent_fix = i + 2  # Start from the line after the else/comment
        break

if start_indent_fix is None:
    print("Could not find target line")
    exit(1)

print(f"Starting indent fix from line {start_indent_fix}")

# Remove one level of indentation (4 spaces) from all lines after start_indent_fix
fixed_lines = lines[:start_indent_fix]
for i in range(start_indent_fix, len(lines)):
    line = lines[i]
    # If line starts with 8 spaces (2 indents), remove 4 spaces (1 indent)
    if line.startswith('        ') and not line.strip().startswith('#'):
        fixed_lines.append(line[4:])
    elif line.startswith('    ') and not line.strip().startswith('#'):
        # This shouldn't happen but keep as is
        fixed_lines.append(line)
    else:
        fixed_lines.append(line)

# Write back
with open('main.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed_lines)

print("✓ Indentation fixed")
