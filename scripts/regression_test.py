#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("audit_engine", root / "scripts" / "audit_engine.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
rules = json.loads((root / "assets" / "rules.json").read_text(encoding="utf-8"))

cases = {
    "service_mortgage": {"file": "service-mortgage-simulated.json", "expect": {"R-CALC-FUND-DEMAND":"PASS", "R-CALC-AMOUNT-DEMAND":"PASS", "R-CALC-YOY":"PASS", "R-CALC-LTV":"PASS", "R-XREF-AMOUNT":"PASS", "R-GOV-EVIDENCE":"PASS", "R-EXT-CREDIT":"NOT_RUN_MISSING_INPUT"}},
    "legacy": {"file": "legacy-service-report.json", "expect": {"R-CALC-FUND-DEMAND":"NOT_RUN_MISSING_INPUT", "R-CALC-LTV":"PASS", "R-XREF-SALES":"WARN", "R-GOV-REDACTION":"PASS", "R-COMP-GUARANTOR":"NOT_APPLICABLE", "R-EXT-TITLE":"NOT_RUN_MISSING_INPUT"}}
}
for name, cfg in cases.items():
    facts = json.loads((root / "assets" / "fixtures" / cfg["file"]).read_text(encoding="utf-8"))
    audit = engine.run(facts, rules)
    statuses = {r["rule_id"]: r["status"] for r in audit["results"]}
    for rule_id, expected in cfg["expect"].items():
        actual = statuses.get(rule_id)
        assert actual == expected, f"{name} {rule_id}: expected {expected}, got {actual}"
    print(f"PASS {name}: {audit['status_counts']}")
print("ALL REGRESSION TESTS PASSED")
