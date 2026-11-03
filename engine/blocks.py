"""공통 원고 블록 — 같은 Markdown이 웹(앱 한 권)에선 움직이고, 인쇄(press)에선 정지 화면이 된다.

    :::용어 편집술 | 축=semantic:9,temporal:6,abstraction:8
    원본을 해체하고 선택하고 재조합하는 기술.
    > 인용문(선택)
    관련: 조합 혁신, K-Atom
    :::

    :::퀴즈 편집술의 세 동작은?
    해체 · 선택 · 재조합
    :::

    :::비교 AI | 편집술
    생성 | 선택 + 재조합
    AI가 완성 | 사람이 완성
    :::

웹: 용어 = 뒤집는 카드(+ 레이더 차트) · 퀴즈 = 눌러서 정답 · 비교 = 줄 강조 표
인쇄: 용어 = 테두리 상자(+ 레이더 차트) · 퀴즈 = 문제 + 작은 글씨 정답 · 비교 = 표
"""
from __future__ import annotations
import html, math, re

AXIS_KO = {"semantic": "의미", "temporal": "시간성", "abstraction": "추상도", "scope": "범위",
           "replaceability": "대체성", "combinability": "결합성", "generativity": "생성력"}
BLOCK = re.compile(r"^:::(용어|퀴즈|비교)[ \t]*(.*?)\n(.*?)^:::[ \t]*$", re.S | re.M)


def radar(axes: dict, size: int = 150, ink: str = "#1d1810", fill: str = "#cfb07a") -> str:
    """7축 레이더 차트(정적 SVG — 웹 · 인쇄 공용)."""
    keys = list(axes); n = len(keys)
    if n < 3:
        return ""
    c = size / 2; r = size * 0.32
    pt = lambda i, v: (c + r * v / 10 * math.sin(2 * math.pi * i / n), c - r * v / 10 * math.cos(2 * math.pi * i / n))
    grid = "".join(f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, lv) for i in range(n)))}" fill="none" stroke="{ink}" stroke-opacity=".18" stroke-width=".6"/>' for lv in (2.5, 5, 7.5, 10))
    spokes = "".join(f'<line x1="{c}" y1="{c}" x2="{pt(i, 10)[0]:.1f}" y2="{pt(i, 10)[1]:.1f}" stroke="{ink}" stroke-opacity=".18" stroke-width=".6"/>' for i in range(n))
    shape = " ".join(f"{x:.1f},{y:.1f}" for x, y in (pt(i, float(axes[k])) for i, k in enumerate(keys)))
    labels = "".join(f'<text x="{pt(i, 13.2)[0]:.1f}" y="{pt(i, 13.2)[1] + 3:.1f}" font-size="8.5" text-anchor="middle" fill="{ink}">{AXIS_KO.get(k, k)}</text>' for i, k in enumerate(keys))
    return (f'<svg class="radar" viewBox="0 0 {size} {size}" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">{grid}{spokes}'
            f'<polygon points="{shape}" fill="{fill}" fill-opacity=".45" stroke="{fill}" stroke-width="1.4"/>{labels}</svg>')


def _axes(spec: str) -> dict:
    m = re.search(r"축\s*=\s*([^|]+)", spec)
    if not m:
        return {}
    out = {}
    for kv in m.group(1).split(","):
        if ":" in kv:
            k, v = kv.split(":", 1)
            try:
                out[k.strip()] = float(v)
            except ValueError:
                pass
    return out


def render(text: str, mode: str = "web") -> str:
    """원고 안의 ::: 블록을 HTML로 바꾼다. mode = web | print. 나머지 Markdown은 그대로 둔다."""
    e = html.escape
    def one(m):
        kind, head, body = m.group(1), m.group(2).strip(), m.group(3).strip()
        if kind == "용어":
            name = head.split("|")[0].strip(); axes = _axes(head)
            lines = body.split("\n"); quote = [l[1:].strip() for l in lines if l.startswith(">")]
            rel = [l.split(":", 1)[1].strip() for l in lines if l.startswith("관련:")]
            defin = " ".join(l for l in lines if l and not l.startswith(">") and not l.startswith("관련:"))
            q = f'<p class="tq">“{e(quote[0])}”</p>' if quote else ""
            r = f'<p class="tr">관련 · {e(rel[0])}</p>' if rel else ""
            chart = radar(axes) if axes else ""
            if mode == "print":
                return f'\n<div class="term"><div class="tb"><b class="tn">{e(name)}</b><p class="td">{e(defin)}</p>{q}{r}</div>{chart}</div>\n'
            return (f'\n<div class="term" tabindex="0"><div class="tf"><b class="tn">{e(name)}</b><span class="tap">눌러서 뜻 보기</span></div>'
                    f'<div class="tbk"><b class="tn">{e(name)}</b><p class="td">{e(defin)}</p>{q}{r}{chart}</div></div>\n')
        if kind == "퀴즈":
            if mode == "print":
                return f'\n<div class="quiz"><p class="qq">문제 · {e(head)}</p><p class="qa">정답 · {e(body)}</p></div>\n'
            return f'\n<div class="quiz"><p class="qq">{e(head)}</p><button class="qb">정답 보기</button><p class="qa" hidden>{e(body)}</p></div>\n'
        if kind == "비교":
            cols = [c.strip() for c in head.split("|")]
            rows = [[c.strip() for c in l.split("|")] for l in body.split("\n") if l.strip()]
            th = "".join(f"<th>{e(c)}</th>" for c in cols)
            tr = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in rows)
            return f'\n<table class="cmp"><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>\n'
        return m.group(0)
    return BLOCK.sub(one, text)


PRINT_CSS = """
.term{display:flex;gap:4mm;align-items:center;border:.6pt solid #000;padding:3mm 4mm;margin:3mm 0;break-inside:avoid}
.term .tb{flex:1}.term .tn{font-family:"Noto Sans CJK KR",sans-serif;font-size:11pt}.term p{text-indent:0;margin:1mm 0}
.term .tq{font-size:9pt;color:#333}.term .tr{font-size:8.6pt;color:#333}.term .radar{width:34mm;height:34mm;flex:none}
.quiz{border-left:1.2pt solid #000;padding:1mm 0 1mm 4mm;margin:3mm 0;break-inside:avoid}.quiz p{text-indent:0;margin:0}
.quiz .qq{font-family:"Noto Sans CJK KR",sans-serif;font-size:9.6pt}.quiz .qa{font-size:8.4pt;color:#444;margin-top:1mm}
table.cmp th{background:#eee}
"""
