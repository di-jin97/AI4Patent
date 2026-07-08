---
name: patent-pct-review
description: PCT申请必要性评审。输入一个Excel（Priority sheet，每行一件专利）和同目录下的DOCX申请文件，对每件专利做5维度评分（1-5分），排序后取前约40%推荐进PCT，输出填好结果的Excel副本。核心依靠Claude的语言理解能力和现有技术检索来分析说明书。
trigger_keywords:
  - 海外评审
  - 专利评审
  - PCT评审
  - 判断专利是否进PCT
  - patent PCT review
  - "patent review"
  - PCT申请评估
  - 巴黎公约部署
---

# Patent PCT Review

## Core Principles

- **You are the executor** — there is no background daemon. Drive each step sequentially; do not "launch the skill" and wait.
- **Analyze using your language understanding, not Python scripts** — patent analysis requires semantic reasoning; scripts only handle I/O, extraction, and scoring math.
- **Read one → score one → persist → immediately read the next** — do not batch-read all files upfront. The context window must stay lean.
- **Finish in one pass** — do not pause in the loop to report or ask for confirmation. Write results directly to JSON.
- **Score based on your independent reading of the specification** — do not be swayed by exaggerated language in the application or the Excel "Significance" column.
- **Write directly into the JSON command and execute** — do not expand long evaluations in your response text, which blows up the context.
- **All temp files go in the current working directory** (not /tmp/).
- **Spread scores across the full 1-5 range** — clustering all patents at 3-4 defeats the purpose of ranking.

---

## Inputs & Outputs

**Input**: An Excel file with a sheet named `Priority` (row 2 = headers, data starts row 5). Column `Patent Ref` contains the patent number. DOCX application files are in the same directory as the Excel.

**Output**: A copy of the Excel with 6 columns filled:
- 发明概述 (≤200 chars)
- 市场价值 (≤100 chars)
- 创新性 (≤100 chars)
- 取证手段 (≤100 chars, includes method + difficulty)
- 可规避性 (≤100 chars)
- Paris Convention Deployment Suggestion ("进PCT" / "不进PCT")

Do not print the Excel content back to the user — just confirm the output file path.

---

## Script Dependencies

This skill requires two Python scripts in the skill's `scripts/` directory:

| Script | Purpose |
|---|---|
| `scripts/extract_key_sections.py` | Extracts claims, technical solution, background, and beneficial effects from a patent DOCX (≤2000 chars) |
| `scripts/score_and_decide.py` | Sorts by total score, selects the top ~40% for PCT, and produces the final decision list |

These are invoked automatically in Phases 2-3. Ensure they exist before starting.

---

## Phase 0: Environment & Prep

Check Python and required libraries; clean up any leftover temp files from a previous run.

```bash
# Check Python availability
python --version || python3 --version || { echo "Python not found. Please install Python 3.x."; exit 1; }

# Install openpyxl if missing
python -c "import openpyxl" 2>/dev/null || pip install openpyxl

# Install python-docx if missing
python -c "import docx" 2>/dev/null || pip install python-docx

# Clean up leftover temp files from previous runs
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new(); Remove-Item -Force ./reviews.jsonl, ./scored.json, ./raw.txt -ErrorAction SilentlyContinue
```

---

## Phase 1: Read Input Data

Read the Excel column headers and build the patent list.

```bash
python -c "
import openpyxl
wb = openpyxl.load_workbook('your_file.xlsx', data_only=True)
ws = wb['Priority']
headers = {cell.value: idx+1 for idx, cell in enumerate(ws[2]) if cell.value}
print('Column mapping:', headers)
patents = []
for row in ws.iter_rows(min_row=5, values_only=False):
    ref = row[headers['Patent Ref']-1].value
    if not ref:
        continue
    patents.append((row[0].row, str(ref).strip()))
print(f'Total patents: {len(patents)}')
for row_num, ref in patents:
    print(f'  Row {row_num}: {ref}')
"
```

Note the column mapping and patent list. **Proceed immediately to Phase 2 for the first patent** — do not wait.

---

## Phase 2: Per-Patent Analysis (Core Work)

**Each patent must complete all four sub-steps (a→d) before moving to the next.**

### Step (a): Read the current patent's detailed fields from Excel

Read only the row for the current patent (use its row number):

```bash
python -c "
import openpyxl
wb = openpyxl.load_workbook('your_file.xlsx', data_only=True)
ws = wb['Priority']
headers = {cell.value: idx+1 for idx, cell in enumerate(ws[2]) if cell.value}
row_num = <ROW_NUMBER>
row = list(ws.iter_rows(min_row=row_num, max_row=row_num, values_only=True))[0]
print('Patent Ref:',         row[headers['Patent Ref']-1])
print('新申请总结:',          row[headers.get('新申请总结', 1)-1])
print('Evaluation History:', row[headers.get('Evaluation History', 1)-1])
print('Whether Adopted:',    row[headers.get('Whether Adopted By Product Or Solution Comments', 1)-1])
print('Significance:',       row[headers.get('Significance', 1)-1])
"
```

After reading this row, **proceed immediately to Step (b)** without reading the next patent.

### Step (b): Match the DOCX file, extract key sections

```bash
python -c "
import glob, re, docx

patent_ref = '<PATENT_REF>'  # replace with the current patent number
digits = re.sub(r'[^0-9]', '', patent_ref)

files = [f for f in glob.glob('**/*.docx', recursive=True) if digits in re.sub(r'[^0-9]', '', f)]
filepath = files[0]
print('Reading file:', filepath)

text = '\n'.join(p.text for p in docx.Document(filepath).paragraphs)
with open('./raw.txt', 'w', encoding='utf-8') as f:
    f.write(text)
"

python "scripts/extract_key_sections.py" ./raw.txt

python -c "open('./raw.txt', 'w').close()"
```

### Step (c): Prior-art search + deep reading + write JSON score

After reading the extracted key sections, **search for 2-3 most relevant prior-art references** to calibrate the innovation assessment.

**Search strategy (in priority order)**:
1. Prefer `exa_web_search_exa` — run 2 searches: one from the technical problem angle, one from the technical solution angle
2. If Exa is unavailable, try other search tools (e.g., `webfetch`, `web_search`)
3. Skip search if no tool is available; analyze based on your own knowledge

Complete the analysis in your reasoning, then **write the result directly into the JSON command below and execute it**. Do not expand long evaluations in response text.

**Scoring rules (spread the scores — avoid clustering):**

| Dimension | Guideline |
|---|---|
| **① market_value_score** — Map from Significance + landing status: High + adopted → 5; High + not adopted → 4; Good + adopted → 4; Good + not adopted → 3; Other (Fair etc.) → 2 |
| **② innovation_score** — Core mechanism fundamentally different from prior art, with real claim壁垒 → 4-5; Meaningful improvement over known solutions, not simple parameter tuning → 3; Difference is only parameter adjustment, known-solution combination, or re-labeling → 1-2 |
| **③ evidence_score** — Pure algorithm/firmware/internal process, not externally observable → ~2; Requires professional testing or partial teardown → 3; Determined by teardown/specs/user manual directly → ~4 |
| **④ circumvention_score** — Other technical paths can achieve similar effects (easily circumvented) → 2-3; No alternative approach achieves the same effect (hard to circumvent) → 4-5 |
| **⑤ landing_score** — Mass-deployed in flagship products → 4-5; Under evaluation or planned → 2-3; No record → 1.5 |

**Total score = sum of all 5 dimensions (range 5-25).** Fill in `total_score`.

For the first patent only, prepend `rm -f ./reviews.jsonl` (to start fresh). For subsequent patents, append to the existing file.

```bash
python -c "
import json
record = {
    'patent_ref': '<PATENT_REF>',
    'row_number': <ROW_NUMBER>,
    'invention_summary': '<发明概述≤200字>',
    'market_value': '<市场价值≤100字>',
    'innovation_text': '<创新性≤100字>',
    'evidence_text': '<取证手段（方式+难度）≤100字>',
    'circumvention_text': '<可规避性≤100字>',
    'innovation_score': 0.0,
    'market_value_score': 0.0,
    'circumvention_score': 0.0,
    'evidence_score': 0.0,
    'landing_score': 0.0,
    'total_score': 0.0,
}
with open('./reviews.jsonl', 'a', encoding='utf-8') as f:
    f.write(json.dumps(record, ensure_ascii=False) + '\n')
print('Written:', record['patent_ref'], 'Score:', record['total_score'])
"
```

### Step (d): Move to the next patent

Take the **next** patent from the list and return to Step (a). Do not pause.

---

## Phase 3: Scoring & Decision

After all patents are scored, sort by total score descending and select the top ~40% for PCT entry (e.g., 4 out of 10). The number of PCT entries **must be > 0** and the ratio must stay **between 35% and 45%**.

```bash
python -c "
import json, sys
sys.path.insert(0, 'scripts')
from score_and_decide import score_and_decide, summarize
reviews = [json.loads(l) for l in open('./reviews.jsonl', encoding='utf-8') if l.strip()]
results = score_and_decide(reviews)
summarize(results)
with open('./scored.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False)
"
```

⚠️ Use `it['final_decision']` directly when writing Excel — do not re-judge.

---

## Phase 4: Excel Output

Copy the input Excel and fill the 6 result columns.

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
    ws.cell(row=row, column=headers['发明概述']).value = r['invention_summary']
    ws.cell(row=row, column=headers['市场价值']).value = r['market_value']
    ws.cell(row=row, column=headers['创新性']).value   = r['innovation_text']
    ws.cell(row=row, column=headers['取证手段']).value = r['evidence_text']
    ws.cell(row=row, column=headers['可规避性']).value = r['circumvention_text']
    ws.cell(row=row, column=headers['Paris Convention Deployment Suggestion']).value = it['final_decision']

wb.save(OUTPUT)
print(f'Saved: {OUTPUT}')
PYEOF
```

Tell the user: output file name, total reviewed count, and PCT-entry ratio. Do not print detailed review content.

---

## Writing Guidelines for the 5 Text Columns

| Column | Guidance |
|---|---|
| **发明概述** | Problem solved + solution used + innovation point. Rewrite based on claims analysis; do not copy application language. |
| **市场价值** | Applicable scenarios/products; whether it has been adopted (check Evaluation History / Whether Adopted). |
| **创新性** | Relative innovation level compared to this batch. Highlight亮点 and note conventional aspects. Do not dismiss everything as trivial. |
| **取证手段** | Method (teardown/parameters/reverse engineering/third-party testing) + difficulty (Easy/Medium/Hard). |
| **可规避性** | Hard to circumvent (broad scope, few alternatives) / Medium / Easy to circumvent (narrowly claimed, changeable by parameter adjustment). |

---

## Quality Checklist

Before finishing, verify:

- [ ] All rows in the patent list were processed (no skipped patents)
- [ ] Each patent has all 5 dimension scores filled (no missing scores)
- [ ] Scores are spread across the 1-5 range, not clustered (e.g., not all at 3-4)
- [ ] Innovation scores are calibrated against prior-art search results (or noted as skipped if no search tool available)
- [ ] The PCT-entry ratio falls between 35% and 45%
- [ ] At least one patent is recommended for PCT entry (ratio > 0)
- [ ] `final_decision` from `score_and_decide.py` is used directly — no manual re-judgment
- [ ] Text columns (发明概述, 市场价值, etc.) each respect their character limits
- [ ] The output Excel is saved as `_reviewed.xlsx` (not overwriting the input)
- [ ] Temp files (reviews.jsonl, scored.json, raw.txt) are present and non-empty before Phase 4 runs