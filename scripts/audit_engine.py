#!/usr/bin/env python3
"""Deterministic checks for normalized operating-loan report facts.

This engine deliberately does not parse source reports or make semantic credit
judgements. WorkBuddy performs semantic extraction; this script only recomputes
auditable formulas and governance invariants.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = ROOT / "assets" / "rules.json"


def get_path(data: dict[str, Any], path: str, default: Any = None) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def supplied(value: Any) -> bool:
    return value is not None and value != "" and value != []


def evidence_ids(facts: dict[str, Any], paths: list[str]) -> list[str]:
    result: list[str] = []
    fact_evidence = facts.get("fact_evidence", {})
    for path in paths:
        for item in fact_evidence.get(path, []):
            if item not in result:
                result.append(item)
    return result


def result(rule: dict[str, Any], status: str, finding: str,
           evidence: list[str] | None = None, calculation: dict[str, Any] | None = None,
           applicability: str = "适用") -> dict[str, Any]:
    return {
        "rule_id": rule["id"], "rule_version": rule["version"],
        "rule_name": rule["name"], "status": status,
        "applicability": applicability, "finding": finding,
        "evidence_ids": evidence or [], "calculation": calculation,
        "executor": rule["executor"], "severity": rule["severity"]
    }


def applicable(rule: dict[str, Any], facts: dict[str, Any]) -> tuple[bool, str]:
    cond = rule.get("applies_if")
    if not cond:
        return True, "无条件规则"
    value = get_path(facts, cond["path"])
    if value in cond.get("in", []):
        return True, f"{cond['path']}={value}"
    return False, f"{cond['path']}={value!r}，不满足适用条件"


def check_fund_demand(rule: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    mode = get_path(facts, "operation.business_type")
    fd = get_path(facts, "fund_demand", {}) or {}
    if mode == "service":
        keys = ["accounts_receivable", "prepayments", "other_receivables", "accounts_payable", "advances_from_customers"]
        formula = "应收账款+预付账款+其他应收款-应付账款-预收账款"
        if not all(supplied(fd.get(k)) for k in keys):
            return result(rule, "NOT_RUN_MISSING_INPUT", "服务类资金需求输入不完整", evidence_ids(facts, [f"fund_demand.{k}" for k in keys]))
        calc = fd["accounts_receivable"] + fd["prepayments"] + fd["other_receivables"] - fd["accounts_payable"] - fd["advances_from_customers"]
    elif mode in ("production", "trade"):
        keys = ["accounts_receivable", "prepayments", "inventory", "accounts_payable", "advances_from_customers"]
        formula = "应收账款+预付账款+存货-应付账款-预收账款"
        if not all(supplied(fd.get(k)) for k in keys):
            return result(rule, "NOT_RUN_MISSING_INPUT", "生产/贸易类资金需求输入不完整", evidence_ids(facts, [f"fund_demand.{k}" for k in keys]))
        calc = fd["accounts_receivable"] + fd["prepayments"] + fd["inventory"] - fd["accounts_payable"] - fd["advances_from_customers"]
    else:
        return result(rule, "NOT_RUN_MISSING_INPUT", "经营类型未可靠归类，无法选择资金需求公式")
    reported = fd.get("reported_demand")
    detail = {"formula": formula, "inputs": {k: fd[k] for k in keys}, "calculated": round(calc, 4), "reported": reported, "unit": "万元"}
    if not supplied(reported):
        return result(rule, "PASS", "已完成复算；报告未给出可比较的测算结果", evidence_ids(facts, [f"fund_demand.{k}" for k in keys]), detail)
    diff = abs(calc - reported)
    detail["difference"] = round(diff, 4)
    status = "PASS" if diff <= 0.01 else "WARN"
    return result(rule, status, "资金需求复算一致" if status == "PASS" else "资金需求复算与报告值不一致", evidence_ids(facts, [f"fund_demand.{k}" for k in keys] + ["fund_demand.reported_demand"]), detail)


def check_amount_demand(rule: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    amount = get_path(facts, "application.amount")
    demand = get_path(facts, "fund_demand.reported_demand")
    if not supplied(amount) or not supplied(demand):
        return result(rule, "NOT_RUN_MISSING_INPUT", "缺少申请金额或资金需求")
    status = "PASS" if amount <= demand + 0.01 else "WARN"
    return result(rule, status, "申请金额未超过资金需求" if status == "PASS" else "申请金额超过资金需求，需说明合理性", evidence_ids(facts, ["application.amount", "fund_demand.reported_demand"]), {"application_amount": amount, "fund_demand": demand, "difference": round(amount-demand, 4), "unit": "万元"})


def check_yoy(rule: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    current = get_path(facts, "operation.sales_current")
    previous = get_path(facts, "operation.sales_previous")
    reported = get_path(facts, "operation.yoy_reported")
    if not supplied(current) or not supplied(previous) or previous == 0:
        return result(rule, "NOT_RUN_MISSING_INPUT", "同比输入缺失或上期为零")
    calc = (current - previous) / previous
    detail = {"formula": "(本期-上期)/上期", "current": current, "previous": previous, "calculated": round(calc, 6), "reported": reported}
    if not supplied(reported):
        return result(rule, "PASS", "已完成同比复算；报告未列示同比值", evidence_ids(facts, ["operation.sales_current", "operation.sales_previous"]), detail)
    diff = abs(calc - reported)
    detail["difference"] = round(diff, 6)
    status = "PASS" if diff <= 0.001 else "WARN"
    return result(rule, status, "同比复算一致" if status == "PASS" else "同比复算与报告值不一致", evidence_ids(facts, ["operation.sales_current", "operation.sales_previous", "operation.yoy_reported"]), detail)


def check_net_asset(rule: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    assets = get_path(facts, "financial.assets_total")
    liabilities = get_path(facts, "financial.liabilities_total")
    reported = get_path(facts, "financial.net_asset_reported")
    if not supplied(assets) or not supplied(liabilities):
        return result(rule, "NOT_RUN_MISSING_INPUT", "资产或负债合计缺失")
    calc = assets - liabilities
    detail = {"formula": "资产合计-负债合计", "assets": assets, "liabilities": liabilities, "calculated": round(calc, 4), "reported": reported, "unit": "万元"}
    if not supplied(reported):
        return result(rule, "PASS", "已完成净资产复算；报告未列示净资产", evidence_ids(facts, ["financial.assets_total", "financial.liabilities_total"]), detail)
    diff = abs(calc - reported)
    detail["difference"] = round(diff, 4)
    status = "PASS" if diff <= 0.01 else "WARN"
    return result(rule, status, "净资产复算一致" if status == "PASS" else "净资产复算与报告值不一致", evidence_ids(facts, ["financial.assets_total", "financial.liabilities_total", "financial.net_asset_reported"]), detail)


def check_ltv(rule: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    secured = get_path(facts, "collateral.secured_amount")
    value = get_path(facts, "collateral.recognized_value")
    reported = get_path(facts, "collateral.ltv_reported")
    if not supplied(secured) or not supplied(value) or value == 0:
        return result(rule, "NOT_RUN_MISSING_INPUT", "担保金额或认可押品价值缺失/为零")
    calc = secured / value
    detail = {"formula": "担保金额/认可押品价值", "secured_amount": secured, "recognized_value": value, "calculated": round(calc, 6), "reported": reported}
    if not supplied(reported):
        return result(rule, "PASS", "已完成抵押率复算；报告未列示抵押率", evidence_ids(facts, ["collateral.secured_amount", "collateral.recognized_value"]), detail)
    diff = abs(calc - reported)
    detail["difference"] = round(diff, 6)
    status = "PASS" if diff <= 0.001 else "WARN"
    return result(rule, status, "抵押率复算一致" if status == "PASS" else "抵押率复算与报告值不一致", evidence_ids(facts, ["collateral.secured_amount", "collateral.recognized_value", "collateral.ltv_reported"]), detail)


def check_consistency(rule: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    values = get_path(facts, rule["input_path"])
    if not isinstance(values, list) or len(values) < 2:
        return result(rule, "NOT_RUN_MISSING_INPUT", "少于两个同口径值，无法交叉比较")
    numbers = [x["value"] if isinstance(x, dict) else x for x in values]
    if not all(isinstance(x, (int, float)) for x in numbers):
        return result(rule, "UNCERTAIN", "比较值含非数值或口径未归一")
    diff = max(numbers) - min(numbers)
    status = "PASS" if abs(diff) <= 0.01 else "WARN"
    ev = []
    for x in values:
        if isinstance(x, dict) and x.get("evidence_id"):
            ev.append(x["evidence_id"])
    return result(rule, status, "报告内同口径值一致" if status == "PASS" else "报告内出现同口径数值差异，需核对期间/主体/口径", ev, {"values": values, "max_difference": round(diff, 4)})


def check_redaction(rule: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    redacted = facts.get("redacted_fields", [])
    missing = facts.get("missing_fields", [])
    overlap = sorted(set(redacted) & set(missing))
    if overlap:
        return result(rule, "FAIL", f"脱敏字段被同时标记为缺失：{', '.join(overlap)}")
    return result(rule, "PASS", f"脱敏字段与缺失字段已区分；脱敏字段数 {len(redacted)}")


def check_evidence(rule: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    evidence = {e.get("evidence_id") for e in facts.get("evidence", [])}
    referenced = {x for ids in facts.get("fact_evidence", {}).values() for x in ids}
    missing = sorted(referenced - evidence)
    if missing:
        return result(rule, "WARN", f"存在未定义的证据编号：{', '.join(missing)}")
    return result(rule, "PASS", f"证据引用完整；已登记 {len(evidence)} 条证据")


OPS = {"fund_demand": check_fund_demand, "amount_vs_demand": check_amount_demand,
       "yoy": check_yoy, "net_asset": check_net_asset, "ltv": check_ltv,
       "consistent_values": check_consistency, "redaction_guard": check_redaction,
       "evidence_integrity": check_evidence}


def run(facts: dict[str, Any], ruleset: dict[str, Any]) -> dict[str, Any]:
    materials = set(facts.get("materials_provided", ["report"]))
    results = []
    for rule in ruleset["rules"]:
        applies, reason = applicable(rule, facts)
        if not applies:
            results.append(result(rule, "NOT_APPLICABLE", reason, applicability=reason))
            continue
        if rule.get("required_material") and rule["required_material"] not in materials:
            results.append(result(rule, "NOT_RUN_MISSING_INPUT", f"未提供所需材料：{rule['required_material']}", applicability=reason))
            continue
        if rule["executor"] == "python":
            results.append(OPS[rule["operation"]](rule, facts))
        else:
            results.append(result(rule, "MANUAL_REVIEW", "需由 WorkBuddy 按语义规则结合证据完成判断", applicability=reason))
    counts: dict[str, int] = {}
    for item in results:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    raw = json.dumps(facts, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {"skill_version": "1.0.0", "ruleset_version": ruleset["ruleset_version"],
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "normalized_input_sha256": hashlib.sha256(raw).hexdigest(),
            "status_counts": counts, "results": results,
            "boundary": "脚本仅执行确定性复算与治理检查；MANUAL_REVIEW 由模型/审批人员结合证据完成。"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("facts", type=Path)
    parser.add_argument("--rules", type=Path, default=RULES_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    facts = json.loads(args.facts.read_text(encoding="utf-8"))
    ruleset = json.loads(args.rules.read_text(encoding="utf-8"))
    audit = run(facts, ruleset)
    text = json.dumps(audit, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


if __name__ == "__main__":
    main()
