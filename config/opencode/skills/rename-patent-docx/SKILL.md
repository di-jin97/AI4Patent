---
name: rename-patent-docx
description: 把当前文件夹下所有 docx 文件重命名为文件名中前8位数字。例如 "92051205CN01 approved app (1).docx" → "92051205.docx"。触发场景：用户提到"重命名专利文件"、"rename patent"、"把专利文件名改成数字"。
---

# Rename Patent Docx

在当前工作目录下，把所有 docx 文件名提取前8位数字作为新文件名：

```bash
python -c "
import os, re, glob

files = glob.glob('*.docx')
for f in files:
    digits = re.sub(r'[^0-9]', '', os.path.splitext(f)[0])
    new_name = digits[:8] + '.docx'
    if f != new_name:
        os.rename(f, new_name)
        print(f'{f} -> {new_name}')
print('完成，共处理', len(files), '个文件')
"
```
