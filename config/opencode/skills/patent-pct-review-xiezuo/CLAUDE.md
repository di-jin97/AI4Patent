# 项目工作约定（patent-pct-review）

## 自动化执行权限

在执行 patent-pct-review 这个 skill 的任务时，以下操作**无需向用户确认**，可以直接执行：

1. **运行 Python 脚本** — 包括 `python xxx.py`、`python -m xxx`、以及调用本 skill `scripts/` 目录下的辅助脚本（如 `match_files.py`、`score_and_decide.py`）。
2. **当前工作目录下的文件操作** — 在用户指定的工作目录（即包含本次任务的 Excel 和专利申请文件的目录、以及输出目录）内进行：
   - 读取文件（PDF / DOC / DOCX / XLSX / TXT 等）
   - 创建临时文件、临时输出
   - 写入 / 覆盖最终输出 Excel（带 `_reviewed` 后缀的那份）
   - 删除自己创建的临时文件
3. **格式转换的本地命令** — 例如 `libreoffice --headless --convert-to docx`、`antiword`、`catdoc` 等，用于把 .doc 转为可读格式。
4. **pip install** — 仅当某个本任务必需的库缺失时（如 openpyxl、python-docx、pypdf 等），可以直接 pip install。

## 仍然需要向用户确认的情况

- **跨目录文件操作** — 如果需要读写当前工作目录之外的路径（比如系统目录、用户的其他项目目录），先问用户。
- **删除非自己创建的文件** — 删除任何不是本次任务临时产生的文件前，先确认。
- **网络访问 / 下载** — 任何对外网的访问（除 pip install 外）先确认。
- **专利文件未找到 / 读取失败** — 这是 skill 的业务规则，必须停下来问用户（与权限无关）。
- **Excel 列名不确定时的列对应关系** — skill 的业务规则，需要用户确认后再继续。

## 简而言之

> 在当前工作目录内、为完成 PCT 评审任务所必需的命令和脚本，直接执行；不要每一步都问"是否运行"。
