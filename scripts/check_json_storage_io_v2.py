#!/usr/bin/env python3
"""Reject new direct Path I/O in the declared audited JSON consumer modules."""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'data/json-storage-consumers-v2.json'
METHODS = {'read_text','read_bytes','write_text','write_bytes','exists','is_file',
           'open','stat','glob','rglob','resolve','unlink'}


def violations(source):
    tree = ast.parse(source)
    modules = {n.asname or n.name.split('.')[0] for item in ast.walk(tree)
               if isinstance(item, ast.Import) for n in item.names}
    modules.update(n.asname or n.name for item in ast.walk(tree)
                   if isinstance(item, ast.ImportFrom) and item.module == 'PIL'
                   for n in item.names if n.name == 'Image')
    result = []
    for n in ast.walk(tree):
        if not isinstance(n,ast.Call):continue
        native=ast.unparse(n.func)
        if native in {'open','os.replace','os.rename','shutil.copyfile','shutil.copy2','os.link',
                      'os.path.exists','os.path.isfile','os.path.getsize'}:
            result.append((n.lineno,ast.dump(n,include_attributes=False)));continue
        if not isinstance(n.func,ast.Attribute) or n.func.attr not in METHODS:continue
        receiver = n.func.value
        if any((isinstance(x,ast.Name) and x.id in {'_StoragePath','__file__'}) or (isinstance(x,ast.Constant) and x.value=='scripts/json_storage_io_v1.py') for x in ast.walk(receiver)):
            continue  # direct-execution import bootstrap, always a .py path
        if isinstance(receiver,ast.Name) and receiver.id in modules | {'storage_io'}:
            continue
        if isinstance(receiver,ast.Attribute) and isinstance(receiver.value,ast.Name) and receiver.value.id in ['os','importlib']:
            continue
        if n.func.attr in ['exists','is_file'] and (n.args or n.keywords):
            continue
        result.append((n.lineno, ast.dump(n, include_attributes=False)))
    return result


def check(root=ROOT, audit_path=AUDIT):
    audit=json.loads(audit_path.read_text());bad=[]
    for row in audit['modules']:
        allowed=set(row.get('physical_exceptions',[])) | set(row.get('nonfilesystem_exceptions',[]))
        for line,expression in violations((root/row['path']).read_text(encoding='utf-8-sig')):
            if expression not in allowed:bad.append(f"{row['path']}:{line}: direct I/O bypasses JSON storage")
    return bad


if __name__=='__main__':
    errors=check()
    print('\n'.join(errors) if errors else 'Declared consumer modules pass the mechanical I/O regression guard')
    raise SystemExit(bool(errors))
