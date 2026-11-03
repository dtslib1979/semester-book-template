"""토목스 프레스 출판 라인 — 원고 하나 넣으면 인쇄소에 올릴 꾸러미까지.

    python pressline.py 원고.txt --title "책 제목" --author "지은이" --printer bookk --size 신국판 --cover dark
    (원고: .txt / .md / .docx · 또는 --text "붙여넣은 글")

순서: 원고 받기 → 장 나누기 → book.json → 빌드(내지 · 표지 · 웹진 · 낭독 대본) → EPUB → 인쇄 전 검사
      → 인쇄소 규격 대조 → <인쇄소>_업로드.zip + 작업지시서.txt
"""
from __future__ import annotations
import argparse, html, json, re, uuid, zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import press

HERE = Path(__file__).resolve().parent
BOOKS = HERE.parent / "_books"  # 밑줄 폴더 = 사이트에 게시되지 않음(원고 보호)
PRINTERS = {k: v for k, v in json.loads((HERE / "printers.json").read_text(encoding="utf-8")).items() if not k.startswith("_")}
COVERS = {"dark": ("#0a1b14", "#efe0bd"), "light": ("#f4efe4", "#1d1810"), "navy": ("#13294b", "#f3e6c4")}

# ── 1. 원고 받기 · 장 나누기 ─────────────────────────────
CHAP = re.compile(r"^\s*(제\s*\d+\s*[장부편화]|\d+\s*장\b|프롤로그|에필로그|들어가며|들어가는\s*말|나가며|나오는\s*말|머리말|맺음말|서문|후기|작가의\s*말|chapter\s*\d+|part\s*\d+|■\s*\S)", re.I)

def read_source(path: Path | None, text: str | None) -> str:
    if text:
        return text
    if path.suffix.lower() == ".docx":
        import docx
        out = []
        for p in docx.Document(str(path)).paragraphs:
            s = (p.style.name if p.style is not None else "").lower(); t = p.text.strip()
            if not t:
                continue
            if s.startswith(("heading 1", "title")) or "제목 1" in s:
                out.append(f"# {t}")
            elif s.startswith("heading 2") or "제목 2" in s:
                out.append(f"## {t}")
            else:
                out.append(t)
        return "\n\n".join(out)
    return path.read_text(encoding="utf-8", errors="ignore")

def is_chapter_line(s: str) -> bool:
    return bool(s) and len(s) <= 40 and bool(CHAP.match(s)) and not re.search(r"(다|요|죠|까)[.?!]?$", s)

def to_chapters(raw: str, title: str) -> list[tuple[str, str]]:
    """'# 제목'이 있으면 그대로. 없으면 '제1장 · 프롤로그 · 1장 · ■ 소제목' 같은 줄을 장 제목으로. 그것도 없으면 한 장."""
    raw = raw.replace("\r\n", "\n").replace("　", " ").strip()
    lines = raw.split("\n")
    if any(l.startswith("# ") for l in lines):
        blocks, cur = [], []
        for l in lines:
            if l.startswith("# ") and cur:
                blocks.append("\n".join(cur)); cur = []
            cur.append(l)
        blocks.append("\n".join(cur))
        return [(re.sub(r"^#\s*", "", b.strip().split("\n")[0]).strip(), b.strip() + "\n") for b in blocks if b.strip()]
    chs, cur_t, cur = [], None, []
    for l in lines:
        s = l.strip()
        if is_chapter_line(s):
            if cur_t is not None or any(x.strip() for x in cur):
                chs.append((cur_t or title, cur))
            cur_t, cur = s, []
        else:
            cur.append(l)
    chs.append((cur_t or title, cur))
    out = []
    for t, body in chs:
        paras = [p.strip() for p in body if p.strip()]
        if paras:
            out.append((t, f"# {t}\n\n" + "\n\n".join(paras) + "\n"))
    return out

# ── 2. EPUB 3 ────────────────────────────────────────────
def build_epub(b: dict, d: Path, out: Path) -> Path:
    e = html.escape; uid = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, b['title'] + b['author'])}"
    chaps = []
    for i, c in enumerate(b["chapters"], 1):
        body, toc = press.md_to_html((d / c).read_text(encoding="utf-8"), 0)
        body = re.sub(r'<span class="footnote">(.*?)</span>', r'<small class="fn"> [주: \1]</small>', body)
        body = body.replace("<br>", "<br/>").replace("<hr>", "<hr/>")
        t = (json.loads(toc) or [[None, b["title"]]])[0][1]
        chaps.append((f"c{i}.xhtml", t, body))
    css = "body{font-family:serif;line-height:1.8;word-break:keep-all}h1{font-size:1.4em;margin:2em 0 1em}p{text-indent:1em;margin:0}.fn{color:#666}"
    p = out / (re.sub(r"[^0-9A-Za-z가-힣]+", "_", b["title"]) + ".epub")
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml", '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles></container>', compress_type=zipfile.ZIP_DEFLATED)
        z.writestr("OEBPS/style.css", css, compress_type=zipfile.ZIP_DEFLATED)
        for f, t, body in chaps:
            z.writestr(f"OEBPS/{f}", f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ko"><head><title>{e(t)}</title><link rel="stylesheet" href="style.css"/></head><body>{body}</body></html>', compress_type=zipfile.ZIP_DEFLATED)
        nav = "".join(f'<li><a href="{f}">{e(t)}</a></li>' for f, t, _ in chaps)
        z.writestr("OEBPS/nav.xhtml", f'<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="ko"><head><title>차례</title></head><body><nav epub:type="toc"><h1>차례</h1><ol>{nav}</ol></nav></body></html>', compress_type=zipfile.ZIP_DEFLATED)
        items = "".join(f'<item id="c{i}" href="{f}" media-type="application/xhtml+xml"{" properties=\"svg\"" if "<svg" in body else ""}/>' for i, (f, _, body) in enumerate(chaps, 1))
        spine = "".join(f'<itemref idref="c{i}"/>' for i in range(1, len(chaps) + 1))
        isbn = f"<dc:source>urn:isbn:{press.isbn_digits(b['isbn'])}</dc:source>" if b.get("isbn") else ""
        z.writestr("OEBPS/content.opf", f'<?xml version="1.0" encoding="utf-8"?>\n<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="ko"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="uid">{uid}</dc:identifier><dc:title>{e(b["title"])}</dc:title><dc:creator>{e(b["author"])}</dc:creator><dc:publisher>{e(b["publisher"])}</dc:publisher><dc:language>ko</dc:language>{isbn}<meta property="dcterms:modified">{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}</meta></metadata><manifest><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/><item id="css" href="style.css" media-type="text/css"/>{items}</manifest><spine>{spine}</spine></package>', compress_type=zipfile.ZIP_DEFLATED)
    return p

# ── 3. 인쇄소 규격 대조 · 작업지시서 · 꾸러미 ─────────────
def printer_check(rep: dict, b: dict, pr: dict) -> list[str]:
    warn, n = [], rep["내지"]["쪽수"]
    if b["size"] not in pr["sizes"]:
        warn.append(f"{pr['name']} 판형 목록에 {b['size']} 없음 — 판형 확인")
    if n < pr["min_pages"]:
        warn.append(f"쪽수 {n}쪽 — {pr['name']} 최소 {pr['min_pages']}쪽 미만(원고를 늘리거나 판형을 작게)")
    if n > pr["max_pages"]:
        warn.append(f"쪽수 {n}쪽 — 최대 {pr['max_pages']}쪽 초과")
    if not pr.get("verified"):
        warn.append(f"{pr['name']} 규격값은 기본값 — 공식 작업 안내로 확인 후 printers.json 수정")
    return warn

def order_sheet(b: dict, rep: dict, pr: dict, paper: str, warn: list[str]) -> str:
    w, h = press.SIZES[b["size"]]
    return "\n".join([f"작업지시서 — {b['title']}", f"작성: {date.today()} · 토목스 프레스", "",
        f"인쇄소: {pr['name']}", f"판형: {b['size']} {w}×{h}mm (파일은 도련 {b['bleed_mm']}mm 포함)",
        f"내지: {rep['내지']['쪽수']}쪽 · 흑백 · {paper} · 무선 제본", f"표지: 4도(CMYK) 단면 · 책등 {rep['책등(mm)']}mm",
        f"ISBN: {b.get('isbn') or '(발급 전)'}", "부수: (적어 주세요)", "",
        "보내는 파일: " + ", ".join(pr["upload"]), f"올리는 곳: {pr['how']}", "", "확인할 점:"] + [f"- {x}" for x in (warn or ["없음"])]) + "\n"

def run(src: Path | None, text: str | None, title: str, author: str, publisher: str = "토목스 프레스", isbn: str = "", size: str = "신국판",
        printer: str = "bookk", paper: str | None = None, cover: str = "dark", subtitle: str = "", blurb: str = "", price: str = "") -> dict:
    pr = PRINTERS[printer]; paper = paper or next(iter(pr["papers"]))
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "-", title).strip("-") or "book"
    d = BOOKS / slug; d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("ch*.md"):
        old.unlink()
    chs = to_chapters(read_source(src, text), title)
    files = []
    for i, (_, body) in enumerate(chs, 1):
        f = f"ch{i:02d}.md"; (d / f).write_text(body, encoding="utf-8"); files.append(f)
    first = [p for p in chs[0][1].split("\n\n")[1:] if p.strip() and not p.startswith("#")]
    bg, fg = COVERS.get(cover, COVERS["dark"])
    b = {"title": title, "subtitle": subtitle, "author": author, "publisher": publisher, "isbn": isbn, "price": price, "size": size,
         "bleed_mm": pr["bleed_mm"], "pad_to": pr["pad_to"], "paper_mm_per_page": pr["papers"][paper], "chapters": files,
         "blurb": blurb or (first[0][:160] if first else ""), "cover_bg": bg, "cover_fg": fg}
    (d / "book.json").write_text(json.dumps(b, ensure_ascii=False, indent=1), encoding="utf-8")
    rep = press.build(d); out = d / "out"; bk = press.load_book(d)
    ep = build_epub(bk, d, out)
    warn = printer_check(rep, bk, pr)
    (out / "작업지시서.txt").write_text(order_sheet(bk, rep, pr, paper, warn), encoding="utf-8")
    zp = out / f"{printer}_업로드.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for f in pr["upload"]:
            z.write(out / f, f)
    hard = [w for w in warn if "기본값" not in w]  # 규격 위반(쪽수 · 판형)은 업로드 불가로
    if hard:
        rep["인쇄소 업로드 가능"] = False
    rep.update({"장": [t for t, _ in chs], "인쇄소": pr["name"], "종이": paper, "인쇄소 확인할 점": warn, "EPUB": ep.name, "꾸러미": zp.name, "폴더": str(d)})
    (out / "preflight.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep

if __name__ == "__main__":
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument("src", nargs="?"); a.add_argument("--text"); a.add_argument("--title", required=True); a.add_argument("--author", required=True)
    a.add_argument("--publisher", default="토목스 프레스"); a.add_argument("--isbn", default=""); a.add_argument("--size", default="신국판")
    a.add_argument("--printer", default="bookk", choices=list(PRINTERS)); a.add_argument("--paper"); a.add_argument("--cover", default="dark", choices=list(COVERS))
    a.add_argument("--subtitle", default=""); a.add_argument("--blurb", default=""); a.add_argument("--price", default="")
    o = a.parse_args()
    r = run(Path(o.src) if o.src else None, o.text, o.title, o.author, o.publisher, o.isbn, o.size, o.printer, o.paper, o.cover, o.subtitle, o.blurb, o.price)
    print(json.dumps({k: r[k] for k in ("장", "인쇄소", "종이", "책등(mm)", "인쇄소 업로드 가능", "인쇄소 확인할 점", "EPUB", "꾸러미", "폴더")}, ensure_ascii=False, indent=1))
