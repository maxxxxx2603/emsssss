#!/usr/bin/env python3
# Add indentation to bot.run() section

with open('main.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find "while retry_count < max_retries:"
start_idx = None
for i, line in enumerate(lines):
    if 'while retry_count < max_retries:' in line:
        start_idx = i + 1
        break

if start_idx is None:
    print("Not found")
    exit(1)

print(f"Indenting from line {start_idx}")

# Add 4 spaces to all lines until EOF
fixed = lines[:start_idx]
for i in range(start_idx, len(lines)):
    line = lines[i]
    # Only add indent if line is not empty or comment-only
    if line.strip():
        fixed.append('    ' + line)
    else:
        fixed.append(line)

with open('main.py', 'w', encoding='utf-8') as f:
    f.writelines(fixed)

print("✓ Done")
