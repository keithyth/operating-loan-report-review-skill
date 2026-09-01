# 证据与状态模型

## 证据层级

- `REPORT_RECORDED`：报告正文、表格、页眉页脚或附件清单中的记载。
- `DETERMINISTIC_CALCULATION`：使用报告数字按公开公式复算的结果。
- `PUBLIC_INFORMATION`：联网查询所得，必须记录来源和查询日期。
- `EXTERNAL_MATERIAL`：用户另行提供的流水、税务、征信、权证、评估等材料。

四层不得静默合并。报告称“征信正常”只能证明客户经理这样记载，不能表述为模型已核验征信。

## 证据记录

每条证据至少包含：

```json
{
  "evidence_id": "E001",
  "layer": "REPORT_RECORDED",
  "source_file": "报告.docx",
  "location": "第3页/经营情况/第2段",
  "quote": "近两年营业收入分别为……",
  "extraction": "native_text",
  "confidence": 0.96
}
```

`quote`只保留支撑判断所需的短句。OCR 低置信度、单位模糊或表格错位必须标记 `UNCERTAIN` 并要求人工核对原件。

## 规则状态

- `PASS`：适用、材料充分且满足规则。
- `WARN`：存在风险、质量不足或轻微偏差，但不等同否决。
- `FAIL`：适用、证据充分，且明确违反硬性要求或出现重大内部矛盾。
- `NOT_APPLICABLE`：条件不成立，例如纯信用业务不执行抵押物规则。
- `NOT_RUN_MISSING_INPUT`：规则适用但缺少执行所需外部材料或关键输入。
- `UNCERTAIN`：证据歧义、OCR 置信度不足、主体匹配不唯一或时点冲突。
- `MANUAL_REVIEW`：需要审批人员作专业判断，模型只呈现依据和争点。

禁止使用“无异常”“已核实”“真实有效”等措辞，除非对应层级的材料确实已提供并完成核验。
