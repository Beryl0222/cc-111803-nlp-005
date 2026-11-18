import json
from pathlib import Path

def load_facts(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def summarize(facts):
    available = {line['line']: line['quantity'] for line in facts['purchase_lines']}
    for declaration in facts['declarations']:
        if declaration['submitted']:
            available[declaration['line']] -= declaration['quantity']
    return available
