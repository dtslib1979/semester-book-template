"""노트(notes/) → site/ : 앱 한 권(index.html) · 인쇄본 PDF · 표지 PDF(CMYK) · 전자책 · 인쇄소 꾸러미(zip) · 검사 결과"""
import json, shutil, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import appbook, press, pressline

notes, site = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
rep = press.build(notes); out = notes / "out"
ep = pressline.build_epub(press.load_book(notes), notes, out)
appbook.build(notes, site, out / "interior.pdf", ep)
for f in ("cover.pdf", "cover_cmyk.pdf", "preflight.json"):
    if (out / f).exists():
        shutil.copy(out / f, site / f)
with zipfile.ZipFile(site / "print-pack.zip", "w", zipfile.ZIP_DEFLATED) as z:  # 인쇄소에 올릴 두 파일
    z.write(out / "interior.pdf", "interior.pdf")
    z.write(out / ("cover_cmyk.pdf" if (out / "cover_cmyk.pdf").exists() else "cover.pdf"), "cover.pdf")
print(json.dumps({k: rep[k] for k in ("책", "판형", "책등(mm)", "인쇄소 업로드 가능")} | {"쪽수": rep["내지"]["쪽수"]}, ensure_ascii=False))
if not rep["인쇄소 업로드 가능"]:
    print("::warning::인쇄 전 검사에서 고칠 점이 있습니다 — site/preflight.json 확인")
