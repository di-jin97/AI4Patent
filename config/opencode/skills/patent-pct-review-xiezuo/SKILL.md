---
name: patent-pct-review
description: 评审专利是否需要申请 PCT。用户提供一个 Excel（Priority sheet，每行一个专利，专利号在 Patent Ref 列）和当前目录下的 DOCX 申请文件。Claude 逐个读取申请文件、用语言能力分析、给 5 维度打分（1-5 分）并算出总分、生成填好结果的 Excel 副本。目标进入 PCT 比例约 40%。触发场景：用户提到"海外评审"、"专利评审"、"PCT 评审"、"判断专利是否进 PCT"、"patent PCT review"。
---

# Patent PCT Review

## 重要原则

- **你就是执行者**，没有后台程序，不要"启动技能"后等待
- **不要写大 Python 脚本**——分析专利靠你自己的语言能力，脚本做不到这件事
- **读一个 → 评一个 → 落盘 → 立刻读下一个**，不要先批量读完所有文件
- **一口气干完**，循环中不要停下来汇报或确认
- **打分基于你独立分析说明书的结果**，不要被申请文件的夸张语言或 Excel 的 Significance 牵着走
- **分析完直接写进 JSON 命令里执行，不要在回复里长篇展开评价**——那样会撑爆上下文
- **所有临时文件建在当前工作目录下**，不要用 /tmp/

## 输入与输出

**输入**：Excel（Priority sheet，第 2 行列名，第 5 行起数据）+ 当前目录下的 DOCX 申请文件

**输出**：原 Excel 副本，将所有评审内容按编号格式填入 `Evaluation Comments` 单列，格式如下：

```
1.创造性：…

2.市场价值：…

3.可取证性：…

4.可规避性：…

5.综合意见：…
```

---

## 第 0 步：删除相关文件

先 `rm -f ./reviews.jsonl` 和 `rm -f ./scored.json` 和 `rm -f ./raw.txt`

---

## 第 1 步：读 Excel 列名和专利号列表

```bash
python -c "
import openpyxl
wb = openpyxl.load_workbook('your_file.xlsx', data_only=True)
ws = wb['Priority']
headers = {cell.value: idx+1 for idx, cell in enumerate(ws[2]) if cell.value}
print('列号映射:', headers)
patents = []
for row in ws.iter_rows(min_row=5, values_only=False):
    ref = row[headers['Patent Ref']-1].value
    if not ref:
        continue
    patents.append((row[0].row, str(ref).strip()))
print(f'共 {len(patents)} 个专利：')
for row_num, ref in patents:
    print(f'  行{row_num}: {ref}')
"
```

记下列号映射和专利清单。**立刻开始第 2 步，对第 1 个专利执行 (a)~(d)**。

---

## 第 2 步：逐个专利分析（核心工作）

**每个专利完整跑完 (a)~(d) 四步才能开始下一个。**

### (a) 从 Excel 读当前专利的详细字段

从专利清单取第 N 个专利的行号，**只读这一行**：

```bash
python -c "
import openpyxl
wb = openpyxl.load_workbook('your_file.xlsx', data_only=True)
ws = wb['Priority']
headers = {cell.value: idx+1 for idx, cell in enumerate(ws[2]) if cell.value}
row_num = <行号>
row = list(ws.iter_rows(min_row=row_num, max_row=row_num, values_only=True))[0]
print('Patent Ref:',         row[headers['Patent Ref']-1])
print('新申请总结:',          row[headers.get('新申请总结', 1)-1])
print('Evaluation History:', row[headers.get('Evaluation History', 1)-1])
print('Whether Adopted:',    row[headers.get('Whether Adopted By Product Or Solution Comments', 1)-1])
print('Significance:',       row[headers.get('Significance', 1)-1])
"
```

读完这一行后**立刻进入 (b)**，不要读下一个专利的数据。

### (b) 按数字匹配 docx 文件，写入 raw.txt，抽关键段

```bash
python -c "
import glob, re, docx

patent_ref = 'CN20231...'  # 替换成当前专利号
digits = re.sub(r'[^0-9]', '', patent_ref)

files = [f for f in glob.glob('**/*.docx', recursive=True) if digits in re.sub(r'[^0-9]', '', f)]
filepath = files[0]
print('读取文件:', filepath)

text = '\n'.join(p.text for p in docx.Document(filepath).paragraphs)
with open('./raw.txt', 'w', encoding='utf-8') as f:
    f.write(text)
"

python "C:\Users\j00815423\.claude\skills\patent-pct-review-xiezuo\scripts\extract_key_sections.py" ./raw.txt

python -c "open('./raw.txt', 'w').close()"
```

### (c) 精读分析 + 直接写入 JSON

读完关键段后，在脑子里完成分析，**直接把结论填进下面命令执行**，不要在回复里写长篇评价（会撑爆上下文）。

**5维度打分规则（打分要拉开差距，不要扎堆在同一分数）**：

**① market_value_score 市场价值**——按 Significance + 落地情况直接对应：
- High + 已落入产品 → 5分
- High + 未落入产品 → 4分
- Good + 已落入产品 → 4分
- Good + 未落入产品 → 3分
- 其他（Fair 等）→ 2分

**② innovation_score 创新性**——你独立判断：
- 技术方案有实质突破，权利要求有真实壁垒 → 4-5分
- 在已知方案上有有意义的改进 → 3分
- 参数调整、已知方案组合、换名包装 → 1-2分

**③ evidence_score 取证便利性**——看侵权行为是否外部可见：
- 纯算法/固件/内部工艺实现，无法从外部判断 → 2分左右
- 需要专业测试或部分拆机 → 3分
- 拆机/规格参数/用户手册即可直接判断 → 4分左右

**④ circumvention_score 抗规避性**——看有没有相似方案能达到相似效果：
- 有其他技术路径可以达到类似效果（可规避）→ 2-3分
- 没有其他方法能达到同样效果，竞品只能用这个方案 → 4-5分

**⑤ landing_score 落地程度**——从 Evaluation History / Whether Adopted 判断：
- 已批量应用主力产品 → 4-5分
- 评估中或有应用计划 → 2-3分
- 无记录 → 1.5分

**总分 = 5个分数之和（5~25分）**，填入 total_score。

分析完成后**立刻填入并执行**（第一个专利先 `rm -f ./reviews.jsonl`）：

```bash
python -c "
import json
record = {
    'patent_ref': 'CN20231...',
    'row_number': 5,
    'creativity_text': '此处填创造性分析（核心发明点+现有技术效果优势+已知检索报告或审查意见+授权前景）',
    'market_value_text': '此处填市场价值（落地商用情况+潜在商用前景+市场规模+地区/国家+友商+标准相关性等）',
    'evidence_text': '此处填可取证性（取证难易度+具体取证方式详细说明：为什么友商会公开/如何具体检测）',
    'circumvention_text': '此处填可规避性（规避难易度+为什么难以规避+技术或商业代价）',
    'final_opinion_text': '此处填综合意见（明确是否进PCT或建议具体国家+主要原因，不重复上面各项内容）',
    'innovation_score': 0.0,
    'market_value_score': 0.0,
    'circumvention_score': 0.0,
    'evidence_score': 0.0,
    'landing_score': 0.0,
    'total_score': 0.0,
}
with open('./reviews.jsonl', 'a', encoding='utf-8') as f:
    f.write(json.dumps(record, ensure_ascii=False) + '\n')
print('已写入:', record['patent_ref'], '总分:', record['total_score'])
"
```

### (d) 立刻进入下一个专利

从专利清单取**下一个**专利的行号，回到 (a)。不停顿。

---

## 第 3 步：排序 + 写 Excel

所有专利评完后，按总分从高到低排序，取分数前约 40% 进 PCT，比如说10个评审，取4个进入：

```bash
python -c "
import json, sys
sys.path.insert(0, r'C:\Users\j00815423\.claude\skills\patent-pct-review-xiezuo\scripts')
from score_and_decide import score_and_decide, summarize
reviews = [json.loads(l) for l in open('./reviews.jsonl', encoding='utf-8') if l.strip()]
results = score_and_decide(reviews)
summarize(results)
with open('./scored.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False)
"
```

⚠️ 进 PCT 数量必须大于 0，比例在 35%~45%。写 Excel 时直接用 `it['final_decision']`，不要自己重新判断。

```bash
python << 'PYEOF'
import shutil, json, openpyxl

INPUT  = 'input.xlsx'
OUTPUT = 'input_reviewed.xlsx'

shutil.copy(INPUT, OUTPUT)
wb = openpyxl.load_workbook(OUTPUT)
ws = wb['Priority']
headers = {c.value: idx+1 for idx, c in enumerate(ws[2]) if c.value}

reviews = {r['patent_ref']: r for r in (json.loads(l) for l in open('./reviews.jsonl', encoding='utf-8') if l.strip())}
scored  = json.load(open('./scored.json', encoding='utf-8'))

for it in scored:
    r, row = reviews[it['patent_ref']], it['row_number']
    if row < 5:
        continue

    comment = (
        f"1.创造性：{r['creativity_text']}\n\n"
        f"2.市场价值：{r['market_value_text']}\n\n"
        f"3.可取证性：{r['evidence_text']}\n\n"
        f"4.可规避性：{r['circumvention_text']}\n\n"
        f"5.综合意见：{r['final_opinion_text']}"
    )
    ws.cell(row=row, column=headers['Evaluation Comments']).value = comment

wb.save(OUTPUT)
print(f'saved: {OUTPUT}')
PYEOF
```

告诉用户：输出文件，评审数量，进/不进 PCT 比例。不需要告诉我具体评审内容。

---

## 评价写作要点

**1. 创造性**：
- 概括该发明的核心发明点，不要复制摘要或申请文件原文，用自己的语言重新表述
- 说明相对于目前了解的现有技术，该发明的技术效果和优势在哪里
- 如有已知检索报告或审查意见，说明对比文件的影响，基于现有技术和已知报告判断授权前景
- 打分参考：技术方案有实质突破、权利要求有真实壁垒 → 4-5分；在已知方案上有有意义的改进 → 3分；参数调整、已知方案组合、换名包装 → 1-2分

**2. 市场价值**：
- 说明我司落地及商用情况（从 Evaluation History / Whether Adopted 判断）
- 潜在商用前景、潜在市场规模、潜在市场地区或国家、潜在友商
- 如涉及公司各类听证、标准相关性、潜高、战略专利包、专家市场应用建议等，一并写入
- 打分按 Significance + 落地情况对应：High + 已落入产品 → 5分；High + 未落入 → 4分；Good + 已落入 → 4分；Good + 未落入 → 3分；其他 → 2分

**3. 可取证性**：
- 明确取证的难易度（易/中/难）
- 详细说明通过什么方式具体如何获取侵权证据，不能泛泛说"通过检测获取"或"通过公开资料获取"
- 公开资料取证：需说明为什么友商会在公开资料中公开该发明方案（如因技术规范、标准符合性、产品手册说明等商业或技术原因）
- 检测取证：需具体解释检测对象、检测方法和步骤，说明侵权行为如何从外部被观测到
- 打分参考：纯算法/固件/内部工艺，无法从外部判断 → 2分左右；需专业测试或部分拆机 → 3分；拆机/规格参数/用户手册即可直接判断 → 4分左右

**4. 可规避性**：
- 明确规避难易度（难规避/中等/易规避）
- 详细解释为什么难以规避：包括技术路径的限制、替代方案的缺失、权利要求覆盖范围等
- 说明规避的技术或商业上的代价（如需重新设计核心架构、性能损失、成本大幅增加等）
- 不要仅说"范围广"或"改参数即可"，需给出具体理由
- 打分参考：有其他技术路径可达到类似效果 → 2-3分；竞品只能用这个方案 → 4-5分

**5. 综合意见**：
- 明确建议：是否申请 PCT，或建议进入的具体国家/地区
- 总结申请或不申请的主要原因，站在整体视角作出判断
- 不要重复上面四项的具体内容，聚焦于最终决策依据

---

## 辅助脚本

位于 `C:\Users\j00815423\.claude\skills\patent-pct-review-xiezuo\scripts\`

- **extract_key_sections.py**：从专利全文抽取权利要求 + 背景 + 有益效果，≤1500 字
- **score_and_decide.py**：按总分排序取前 40% 进 PCT
