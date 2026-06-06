import sys
import re

def build_and_print_tree():
    tree = {}
    # Read paths streamed directly from git ls-files
    for line in sys.stdin:
        parts = line.strip().split('/')
        if not parts or parts[0].startswith('.'):
            continue
        current = tree
        for part in parts:
            current = current.setdefault(part, {})

def build_tree():
    tree = {}
    # Parse tracked git paths into a nested dictionary layout
    for line in sys.stdin:
        line = line.strip()
        if not line or line.startswith('.'):
            continue
        parts = line.split('/')
        current = tree
        for part in parts:
            current = current.setdefault(part, {})
    return tree

def print_tree(node, prefix=""):
    items = sorted(node.keys())
    for i, key in enumerate(items):
        is_last = (i == len(items) - 1)
        # Choose matching ASCII tree symbols based on position layout
        connector = "└── " if is_last else "├── "
        print(f"{prefix}{connector}{key}")
        
        # Recurse deeper into nested folders using appropriate spacing tracks
        if node[key]:
            next_prefix = prefix + ("    " if is_last else "│   ")
            print_tree(node[key], next_prefix)
            
def show_old(d, indent=0):
    for k, v in sorted(d.items()):
        print('  ' * indent + k)
        show(v, indent + 1)

# Recursive function to print matching indented text
def show(d, indent=0):
    # Sort folders before files alphabetically
    for k, v in sorted(d.items(), key=lambda x: (len(x[1]) == 0, x[0])):
        print('  ' * indent + k)
        show(v, indent + 1)

def extract_readme_style():
    """Safely extracts the ## Project Structure section, handling any emojis or formatting."""
    try:
        content = open('README.md', encoding='utf-8').read()
        # Find the header regardless of symbols/emojis and stop right before the next heading
        match = re.search(r'(?s)(## .*?Project Structure.*?\n)(.*?)(?=\n## )', content)
        if match:
            print(match.group(1) + match.group(2))
        else:
            print("ERROR: 'Project Structure' heading layout not found inside README.md")
    except FileNotFoundError:
        print("ERROR: README.md file could not be opened or found at the project root")

            
if __name__ == '__main__':
    # build_and_print_tree()
    # Determine execution task based on incoming terminal arguments
    if len(sys.argv) > 1 and sys.argv[1] == '--readme':
        extract_readme_style()
    else:
        git_tree = build_tree()
        print_tree(git_tree)