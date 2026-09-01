#!/usr/bin/env python3
import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
errors = []
files = [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts]
allowed = {".md", ".py", ".js", ".txt", ".json", ".yaml", ".yml"}
allowed_names = {".gitignore"}
if not (root / "SKILL.md").is_file(): errors.append("SKILL.md 不在包根目录")
if len(files) > 300: errors.append(f"文件数 {len(files)} 超过 300")
size = sum(p.stat().st_size for p in files)
if size > 10 * 1024 * 1024: errors.append("包大小超过 10MB")
for p in files:
    if p.suffix.lower() not in allowed and p.name not in allowed_names: errors.append(f"不允许的文件类型：{p.relative_to(root)}")
    try: p.read_text(encoding="utf-8")
    except UnicodeDecodeError: errors.append(f"非 UTF-8 文本：{p.relative_to(root)}")
skill = (root / "SKILL.md").read_text(encoding="utf-8") if (root / "SKILL.md").exists() else ""
fm = re.match(r"^---\s*\n(.*?)\n---\s*\n", skill, re.S)
if not fm: errors.append("SKILL.md 缺少有效 frontmatter")
else:
    name = re.search(r"^name:\s*(.+)$", fm.group(1), re.M)
    desc = re.search(r"^description:\s*(.+)$", fm.group(1), re.M)
    if not name or not re.fullmatch(r"[a-z0-9-]{3,64}", name.group(1).strip()): errors.append("name 格式无效")
    if not desc or not (1 <= len(desc.group(1).strip()) <= 1024): errors.append("description 长度无效")
for link in re.findall(r"\]\((references/[^)]+)\)", skill):
    if not (root / link).is_file(): errors.append(f"引用文件不存在：{link}")
for p in root.rglob("*.json"):
    try: json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc: errors.append(f"JSON 无效 {p.relative_to(root)}：{exc}")
rules_path = root / "assets" / "rules.json"
if rules_path.exists():
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    ids = [r.get("id") for r in data.get("rules", [])]
    if len(ids) != len(set(ids)): errors.append("规则编号重复")
    required = {"id", "version", "name", "category", "type", "executor", "severity", "source"}
    for idx, rule in enumerate(data.get("rules", []), 1):
        miss = required - set(rule)
        if miss: errors.append(f"第 {idx} 条规则缺字段：{sorted(miss)}")
if errors:
    print("VALIDATION FAILED")
    for e in errors: print(f"- {e}")
    raise SystemExit(1)
print(f"VALIDATION PASSED: {len(files)} files, {size} bytes")
