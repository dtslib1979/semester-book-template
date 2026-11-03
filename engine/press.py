"""토목스 프레스 — 원고(Markdown) + 책 정보(book.json) → 인쇄소 직송 파일.

    python press.py build <책 폴더>      # out/ 에 아래 파일을 만든다

  interior.pdf      내지 — 판형 + 도련(bleed) · 재단선 · 표제지 · 목차 · 장은 오른쪽 쪽에서 시작 · 머리글 · 쪽번호 · 판권지
  cover.pdf         표지 펼침면 — 뒤표지 · 책등 · 앞표지 + 도련 · 책등 폭은 쪽수로 계산 · ISBN 바코드(EAN-13)
  cover_cmyk.pdf    표지 CMYK 변환본(Ghostscript가 있을 때)
  webzine.html      같은 원고의 웹진판(한 장짜리 HTML)
  audiobook.txt     같은 원고의 낭독 대본(문단 · 쉼 표시)
  preflight.json    인쇄 전 검사 결과(판형 · 도련 · 쪽수 · 글꼴 포함 · ISBN 검증 · 책등 폭)

외부 서비스 없음 · 내 PC에서 실행 · 엔진 = WeasyPrint(오픈소스, CSS Paged Media).
"""
from __future__ import annotations
import html, json, math, re, shutil, subprocess, sys
from datetime import date
from pathlib import Path

import markdown
import blocks
from weasyprint import CSS, HTML
from pypdf import PdfReader

HERE = Path(__file__).resolve().parent
SIZES = json.loads((HERE / "sizes.json").read_text(encoding="utf-8"))


# ── 책 정보 ──────────────────────────────────────────────
def load_book(d: Path) -> dict:
    b = json.loads((d / "book.json").read_text(encoding="utf-8"))
    b.setdefault("size", "신국판"); b.setdefault("bleed_mm", 3); b.setdefault("margins_mm", [20, 17, 22, 20])  # 위 · 바깥 · 아래 · 안쪽
    b.setdefault("paper_mm_per_page", 0.05); b.setdefault("pad_to", 2); b.setdefault("subtitle", ""); b.setdefault("blurb", "")
    b.setdefault("edition", f"{date.today():%Y년 %-m월 %-d일} 초판 1쇄"); b.setdefault("chapters", ["원고.md"])
    return b


# ── ISBN-13 · EAN-13 바코드 ───────────────────────────────
def isbn_digits(isbn: str) -> str:
    return re.sub(r"\D", "", isbn or "")

def isbn_ok(isbn: str) -> bool:
    d = isbn_digits(isbn)
    if len(d) != 13 or not d.startswith(("978", "979")):
        return False
    s = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d[:12]))
    return (10 - s % 10) % 10 == int(d[12])

L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]

def ean13_svg(isbn: str, w_mm: float = 37.3, h_mm: float = 25.9) -> str:
    """EAN-13 표준 인코딩(공개 규격). 숫자는 아래에, ISBN 문자열은 위에."""
    d = isbn_digits(isbn)
    bits = "101" + "".join((L if PARITY[int(d[0])][i] == "L" else G)[int(c)] for i, c in enumerate(d[1:7])) + "01010" + "".join(R[int(c)] for c in d[7:13]) + "101"
    m = w_mm / (len(bits) + 18)  # 양옆 조용한 영역
    guard = {0, 1, 2, 45, 46, 47, 48, 49, 92, 93, 94}
    bars = []; x0 = 11 * m
    for i, b in enumerate(bits):
        if b == "1":
            hh = h_mm - 6.5 + (2.2 if i in guard else 0)
            bars.append(f'<rect x="{x0 + i * m:.3f}" y="4" width="{m:.3f}" height="{hh:.3f}"/>')
    t = lambda x, s, a="middle": f'<text x="{x:.2f}" y="{h_mm - 0.4:.2f}" font-size="2.6" text-anchor="{a}" font-family="Noto Sans CJK KR">{s}</text>'
    nums = t(x0 - 1.2 * m, d[0], "end") + t(x0 + 24 * m, d[1:7]) + t(x0 + 70 * m, d[7:13])
    head = f'<text x="{w_mm / 2:.2f}" y="3" font-size="2.6" text-anchor="middle" font-family="Noto Sans CJK KR">ISBN {d[:3]}-{d[3:5]}-{d[5:9]}-{d[9:12]}-{d[12]}</text>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{w_mm}mm" height="{h_mm}mm" viewBox="0 0 {w_mm} {h_mm}"><rect width="{w_mm}" height="{h_mm}" fill="#fff"/><g fill="#000">{"".join(bars)}</g>{head}{nums}</svg>'


# ── 원고 → HTML (장 · 각주) ────────────────────────────────
EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F]")

def md_to_html(text: str, chap_no: int) -> tuple[str, str]:
    text = EMOJI.sub("", text)
    text = blocks.render(text, "print")  # ::: 용어 · 퀴즈 · 비교 → 인쇄용 상자 · 표
    """# = 장 제목(한 파일에 여러 개 가능). [^n] 각주는 그 쪽 아래로 흐르는 각주(float: footnote)."""
    defs = dict(re.findall(r"^\[\^([^\]]+)\]:\s*(.+)$", text, re.M))
    text = re.sub(r"^\[\^([^\]]+)\]:.*$", "", text, flags=re.M)
    text = re.sub(r"\[\^([^\]]+)\]", lambda m: f'<span class="footnote">{html.escape(defs.get(m.group(1), ""))}</span>', text)
    body = markdown.markdown(text, extensions=["tables", "sane_lists"])
    toc = []
    def h1(m):
        nonlocal chap_no
        chap_no += 1; t = re.sub("<[^>]+>", "", m.group(1)); toc.append((f"ch{chap_no}", t))
        return f'<h1 class="chapter" id="ch{chap_no}">{m.group(1)}</h1>'
    body = re.sub(r"<h1>(.*?)</h1>", h1, body)
    return body, json.dumps(toc, ensure_ascii=False)

def page_css(b: dict, w: float, h: float) -> str:
    t, o, btm, i = b["margins_mm"]; bl = b["bleed_mm"]
    head = html.escape(b["title"])
    return f"""
@page {{ size:{w}mm {h}mm; bleed:{bl}mm; marks:crop; margin:{t}mm {o}mm {btm}mm {i}mm;
  @bottom-center {{ content:counter(page); font-family:\"Noto Sans CJK KR\",sans-serif; font-size:7.8pt; }} }}
@page :left {{ margin-left:{o}mm; margin-right:{i}mm; @top-left {{ content:"{head}"; font-family:\"Noto Sans CJK KR\",sans-serif; font-size:7.5pt; }} }}
@page :right {{ margin-left:{i}mm; margin-right:{o}mm; @top-right {{ content:string(chapter); font-family:\"Noto Sans CJK KR\",sans-serif; font-size:7.5pt; }} }}
@page :blank {{ @top-left {{ content:none }} @top-right {{ content:none }} @bottom-center {{ content:none }} }}
@page front {{ @bottom-center {{ content:none }} @top-left {{ content:none }} @top-right {{ content:none }} }}
@page back {{ @bottom-center {{ content:none }} @top-left {{ content:none }} @top-right {{ content:none }} }}
@page :first {{ @bottom-center {{ content:none }} }}
"""

def interior_html(b: dict, d: Path) -> str:
    parts, toc, n = [], [], 0
    for c in b["chapters"]:
        body, t = md_to_html((d / c).read_text(encoding="utf-8"), n)
        t = json.loads(t); toc += t; n += len(t); parts.append(body)
    e = html.escape
    toc_html = "".join(f'<li><a href="#{a}">{e(x)}</a></li>' for a, x in toc)
    isbn = b.get("isbn", "")
    col = [("지은이", b["author"]), ("펴낸곳", b["publisher"]), ("출판등록", b.get("publisher_reg", "")), ("주소", b.get("address", "")),
           ("전자우편", b.get("email", "")), ("ISBN", isbn), ("값", b.get("price", ""))]
    col_html = "".join(f"<tr><td>{e(k)}</td><td>{e(v)}</td></tr>" for k, v in col if v)
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>{e(b['title'])}</title></head><body>
<section class="title-page"><h1 class="t">{e(b['title'])}</h1><div class="sub">{e(b['subtitle'])}</div><div class="au">{e(b['author'])} 지음</div><div class="pub">{e(b['publisher'])}</div></section>
<nav class="toc"><h2>차례</h2><ol>{toc_html}</ol></nav>
{''.join(parts)}
<section class="colophon"><div class="t">{e(b['title'])}</div><div>{e(b['edition'])}</div><table>{col_html}</table>
<p class="noindent" style="margin-top:4mm">이 책의 저작권은 지은이에게 있습니다. 잘못 만들어진 책은 바꾸어 드립니다.</p></section>
</body></html>"""


# ── 표지 펼침면 ──────────────────────────────────────────
def cover_html(b: dict, w: float, h: float, spine: float) -> tuple[str, str]:
    """페이지 = 재단 크기(뒤표지 + 책등 + 앞표지), 도련은 @page bleed로 바깥에 붙인다."""
    bl = b["bleed_mm"]; W = round(2 * w + spine, 2); e = html.escape
    bg = b.get("cover_bg", "#0a1b14"); fg = b.get("cover_fg", "#efe0bd")
    bar = ean13_svg(b["isbn"]) if isbn_ok(b.get("isbn", "")) else ""
    css = f"@page{{size:{W}mm {h}mm;margin:0;bleed:{bl}mm;marks:crop;background:{bg}}}"
    hf = "font-family:'Noto Sans CJK KR',sans-serif"
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"></head><body style="margin:0">
<div style="position:relative;width:{W}mm;height:{h}mm;color:{fg};{hf}">
 <div style="position:absolute;left:14mm;top:22mm;width:{w - 28}mm;font-family:'NanumMyeongjo',serif;font-size:9.5pt;line-height:1.8">{e(b['blurb'])}</div>
 <div style="position:absolute;left:{w - 14 - 37.3}mm;top:{h - 14 - 25.9}mm;width:37.3mm;height:25.9mm">{bar}</div>
 <div style="position:absolute;left:14mm;top:{h - 22}mm;font-size:8pt">{e(b.get('price', ''))}</div>
 <div style="position:absolute;left:{w}mm;top:0;width:{spine}mm;height:{h}mm;display:flex;align-items:center;justify-content:center">
   {"" if spine < 6 else f'<div style="writing-mode:vertical-rl;font-size:{min(9, spine * 0.62):.1f}pt;white-space:nowrap">{e(b["title"])} · {e(b["author"])} · {e(b["publisher"])}</div>'}</div>
 <div style="position:absolute;left:{w + spine + 16}mm;top:40mm;width:{w - 32}mm">
   <div style="font-size:24pt;font-weight:700;line-height:1.3">{e(b['title'])}</div>
   <div style="margin-top:6mm;font-size:11pt;opacity:.85">{e(b['subtitle'])}</div>
   <div style="margin-top:22mm;font-size:12pt">{e(b['author'])} 지음</div></div>
 <div style="position:absolute;left:{w + spine + 16}mm;top:{h - 26}mm;font-size:10pt;letter-spacing:.2em">{e(b['publisher'])}</div>
</div></body></html>"""
    return doc, css


# ── 웹진 · 낭독 대본 ─────────────────────────────────────
def webzine(b: dict, inner: str) -> str:
    e = html.escape
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(b['title'])}</title>
<style>body{{margin:0;background:#faf8f3;color:#1a1a1a;font:17px/1.85 "Noto Serif KR","Nanum Myeongjo",serif;word-break:keep-all}}main{{max-width:680px;margin:0 auto;padding:48px 20px}}
h1{{font-family:"Pretendard",sans-serif;margin:2.2em 0 .8em}}p{{margin:0 0 1em}}blockquote{{border-left:3px solid #c9a35c;margin:1em 0;padding:.2em 1em;color:#444}}.footnote{{font-size:.8em;color:#666}}.footnote::before{{content:" ※ "}}</style></head>
<body><main><p style="letter-spacing:.2em;color:#8a6a2c">{e(b['publisher'])}</p><h1 style="margin-top:0;font-size:2em">{e(b['title'])}</h1><p>{e(b['author'])}</p>{inner}</main></body></html>"""

def audiobook(b: dict, d: Path) -> str:
    out = [f"[제목] {b['title']} — {b['author']} 지음", "[쉼 2초]"]
    for c in b["chapters"]:
        for blk in re.split(r"\n\s*\n", (d / c).read_text(encoding="utf-8")):
            blk = re.sub(r"\[\^[^\]]+\]:.*", "", blk); blk = re.sub(r"\[\^[^\]]+\]", "", blk)
            if not blk.strip() or blk.strip().startswith("|") or blk.strip().startswith("```") or re.fullmatch(r"[-*_=\s]{3,}", blk.strip()):
                continue
            if blk.startswith("# "):
                out += ["[쉼 2초]", f"[장] {blk[2:].strip()}", "[쉼 1초]"]; continue
            t = re.sub(r"[#>*_`]+", "", blk).strip()
            t = re.sub(r"\s*\n\s*", " ", t)
            if t:
                out += [t, "[쉼 0.6초]"]
    return "\n".join(out) + "\n"


# ── 인쇄 전 검사 ─────────────────────────────────────────
def preflight(pdf: Path, w: float, h: float, bl: float, b: dict, kind: str, expect_w: float | None = None) -> dict:
    r = PdfReader(str(pdf)); pt = 72 / 25.4
    p0 = r.pages[0]; mb = p0.mediabox; tb = p0.trimbox
    trim = (round(float(tb.width) / pt, 1), round(float(tb.height) / pt, 1))
    media = (round(float(mb.width) / pt, 1), round(float(mb.height) / pt, 1))
    fonts, unembedded = set(), set()
    for pg in r.pages[:40]:
        res = pg.get("/Resources") or {}
        for f in (res.get("/Font") or {}).values():
            f = f.get_object(); name = str(f.get("/BaseFont", "")); fonts.add(name)
            desc = f.get("/FontDescriptor")
            if desc is None and "/DescendantFonts" in f:
                desc = f["/DescendantFonts"][0].get_object().get("/FontDescriptor")
            if desc is not None:
                desc = desc.get_object()
                if not any(k in desc for k in ("/FontFile", "/FontFile2", "/FontFile3")):
                    unembedded.add(name)
    want = (expect_w or w, h)
    ok_trim = abs(trim[0] - want[0]) < 0.6 and abs(trim[1] - want[1]) < 0.6
    ok_bleed = abs(media[0] - trim[0] - 2 * bl) < 0.6 and abs(media[1] - trim[1] - 2 * bl) < 0.6
    res = {"파일": pdf.name, "쪽수": len(r.pages), "재단 크기(mm)": trim, "도련 포함(mm)": media,
           "판형 일치": ok_trim, f"도련 {bl}mm": ok_bleed, "글꼴": sorted(fonts)[:8], "글꼴 모두 포함": not unembedded}
    if kind == "interior":
        res["짝수 쪽"] = len(r.pages) % 2 == 0
    return res


# ── 빌드 ────────────────────────────────────────────────
def build(d: Path) -> dict:
    b = load_book(d); w, h = SIZES[b["size"]]; out = d / "out"; out.mkdir(exist_ok=True)
    base = CSS(string=(HERE / "book.css").read_text(encoding="utf-8") + blocks.PRINT_CSS)
    src = interior_html(b, d)
    doc = HTML(string=src, base_url=str(d)).render(stylesheets=[base, CSS(string=page_css(b, w, h))])
    n = len(doc.pages); pad = (-n) % int(b["pad_to"])
    if pad:  # 인쇄소가 요구하는 배수(2 · 4 …)로 빈 쪽 채우기
        src = src.replace("</body>", '<div style="break-before:page"></div>' * pad + "</body>")
        doc = HTML(string=src, base_url=str(d)).render(stylesheets=[base, CSS(string=page_css(b, w, h))])
        n = len(doc.pages)
    doc.write_pdf(out / "interior.pdf")
    spine = round(n * b["paper_mm_per_page"] + b.get("cover_board_mm", 0.5), 1)
    chtml, ccss = cover_html(b, w, h, spine)
    HTML(string=chtml).write_pdf(out / "cover.pdf", stylesheets=[base, CSS(string=ccss)])
    inner = "".join(md_to_html((d / c).read_text(encoding="utf-8"), 0)[0] for c in b["chapters"])
    (out / "webzine.html").write_text(webzine(b, inner), encoding="utf-8")
    (out / "audiobook.txt").write_text(audiobook(b, d), encoding="utf-8")
    cmyk = None
    if shutil.which("gs"):
        r = subprocess.run(["gs", "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite", "-sColorConversionStrategy=CMYK",
                            "-dProcessColorModel=/DeviceCMYK", "-dEmbedAllFonts=true", f"-sOutputFile={out / 'cover_cmyk.pdf'}", str(out / "cover.pdf")],
                           capture_output=True, text=True)
        cmyk = r.returncode == 0
    W = round(2 * w + spine, 2)
    rep = {"책": b["title"], "판형": f"{b['size']} {w}×{h}mm", "책등(mm)": spine,
           "ISBN": b.get("isbn", ""), "ISBN 검증": isbn_ok(b.get("isbn", "")) if b.get("isbn") else "없음(발급 후 입력)",
           "내지": preflight(out / "interior.pdf", w, h, b["bleed_mm"], b, "interior"),
           "표지": preflight(out / "cover.pdf", w, h, b["bleed_mm"], b, "cover", expect_w=W), "표지 CMYK": cmyk,
           "만든 파일": sorted(p.name for p in out.iterdir())}
    rep["책등 글자"] = "넣음" if spine >= 6 else "생략(책등 6mm 미만 — 얇은 책은 글자를 넣지 않는 것이 관례)"
    try:  # 바코드를 실제로 읽어 ISBN과 대조
        import zxingcpp
        from PIL import Image
        png = out / "_cover_check.png"
        subprocess.run(["gs", "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pnggray", "-r400", f"-sOutputFile={png}", str(out / "cover.pdf")], check=True)
        got = [x.text for x in zxingcpp.read_barcodes(Image.open(png))]; png.unlink()
        rep["바코드 판독"] = (isbn_digits(b.get("isbn", "")) in got) if b.get("isbn") else "ISBN 없음"
    except Exception as ex:
        rep["바코드 판독"] = f"검사 못 함({ex.__class__.__name__})"
    rep["인쇄소 업로드 가능"] = bool(rep["내지"]["판형 일치"] and rep["내지"][f"도련 {b['bleed_mm']}mm"] and rep["내지"]["글꼴 모두 포함"] and rep["내지"]["짝수 쪽"]
                                and rep["표지"]["글꼴 모두 포함"] and rep["ISBN 검증"] is not False and rep.get("바코드 판독") is not False)
    (out / "preflight.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] != "build":
        print(__doc__); sys.exit(1)
    print(json.dumps(build(Path(sys.argv[2]).resolve()), ensure_ascii=False, indent=1))
