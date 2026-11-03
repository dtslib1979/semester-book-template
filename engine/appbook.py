"""앱 한 권(interactive book) — 같은 원고(book.json + Markdown)를 설치형 웹앱 책 한 권으로.

    python appbook.py <책 폴더> <내보낼 폴더> [--pdf 인쇄본.pdf --epub 전자책.epub]

나오는 것: index.html(책 한 권 = 앱 하나) · manifest.webmanifest · icon.svg (+ 인쇄본 · 전자책 사본)
규격(앱 한 권): 표지 · 차례 · 장 넘기기(밀기 · 화살표) · 진행 막대 · 글자 크기 · 밤 화면 · 찾기 · 책갈피 · 판권 · 인쇄본/전자책 받기
원칙: Service Worker 쓰지 않음(eae-univ 헌법 §8 — Edge 읽어주기 · 크롬 번역 보존). 바깥 서버 없음.
"""
from __future__ import annotations
import argparse, html, json, re, shutil
from pathlib import Path

import markdown
import blocks

HERE = Path(__file__).resolve().parent


def chapters(d: Path, b: dict) -> list[tuple[str, str]]:
    out = []
    for c in b["chapters"]:
        text = blocks.render((d / c).read_text(encoding="utf-8"), "web")
        text = re.sub(r"\[\^([^\]]+)\]:\s*(.+)$", r'<aside class="fn" data-fn="\1">\2</aside>', text, flags=re.M)
        text = re.sub(r"\[\^([^\]]+)\]", r'<sup class="fr">\1</sup>', text)
        parts = re.split(r"^# (.+)$", text, flags=re.M)
        if parts[0].strip():
            out.append((b["title"], markdown.markdown(parts[0], extensions=["tables", "sane_lists"])))
        for i in range(1, len(parts), 2):
            out.append((parts[i].strip(), markdown.markdown(parts[i + 1], extensions=["tables", "sane_lists"])))
    return out


def icon_svg(b: dict) -> str:
    ch = html.escape(b["title"][:1])
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="96" fill="{b.get("cover_bg", "#0a1b14")}"/>'
            f'<rect x="56" y="56" width="400" height="400" rx="60" fill="none" stroke="{b.get("cover_fg", "#efe0bd")}" stroke-width="10" opacity=".6"/>'
            f'<text x="256" y="330" font-size="230" text-anchor="middle" font-family="Noto Serif KR,serif" font-weight="900" fill="{b.get("cover_fg", "#efe0bd")}">{ch}</text></svg>')


def build(d: Path, out: Path, pdf: Path | None = None, epub: Path | None = None) -> Path:
    b = json.loads((d / "book.json").read_text(encoding="utf-8")); e = html.escape
    chs = chapters(d, b); out.mkdir(parents=True, exist_ok=True)
    (out / "icon.svg").write_text(icon_svg(b), encoding="utf-8")
    (out / "manifest.webmanifest").write_text(json.dumps({"name": b["title"], "short_name": b["title"][:12], "start_url": "./", "display": "standalone",
        "background_color": b.get("cover_bg", "#0a1b14"), "theme_color": b.get("cover_bg", "#0a1b14"), "lang": "ko",
        "icons": [{"src": "icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}]}, ensure_ascii=False), encoding="utf-8")
    dl = []
    if pdf and pdf.exists():
        shutil.copy(pdf, out / "print.pdf"); dl.append('<a href="print.pdf" target="_blank">인쇄본 PDF</a>')
    if epub and epub.exists():
        shutil.copy(epub, out / "book.epub"); dl.append('<a href="book.epub" download>전자책 EPUB</a>')
    toc = "".join(f'<li><button data-go="{i + 1}"><em>{i + 1:02d}</em>{e(t)}</button></li>' for i, (t, _) in enumerate(chs))
    pages = "".join(f'<section class="pg" data-i="{i + 1}"><h1>{e(t)}</h1>{body}</section>' for i, (t, body) in enumerate(chs))
    bg, fg = b.get("cover_bg", "#0a1b14"), b.get("cover_fg", "#efe0bd")
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>{e(b['title'])}</title><meta name="description" content="{e(b.get('subtitle') or b.get('blurb', ''))}">
<link rel="manifest" href="manifest.webmanifest"><link rel="icon" href="icon.svg"><meta name="theme-color" content="{bg}">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;700;900&family=Noto+Sans+KR:wght@400;700&display=swap">
<style>
:root{{--bg:#faf7f0;--ink:#1c1a16;--mute:#6d665a;--line:#e3dccd;--acc:#a8843e;--card:#fff;--cbg:{bg};--cfg:{fg};--fs:18px}}
body.night{{--bg:#0e1411;--ink:#e9e3d6;--mute:#9aa49e;--line:#26332c;--acc:#cfb07a;--card:#152019}}
*{{box-sizing:border-box}}[hidden]{{display:none!important}}html,body{{margin:0}}body{{background:var(--bg);color:var(--ink);font:var(--fs)/1.85 "Noto Serif KR",serif;word-break:keep-all;transition:background .3s}}
.bar{{position:fixed;inset:0 0 auto;z-index:20;display:flex;align-items:center;gap:6px;padding:calc(env(safe-area-inset-top) + 8px) 12px 8px;background:color-mix(in srgb,var(--bg) 88%,transparent);backdrop-filter:blur(10px);border-bottom:1px solid var(--line);font:600 14px "Noto Sans KR",sans-serif}}
.bar b{{flex:1;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}}.bar button{{border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:999px;padding:6px 11px;font:inherit;cursor:pointer}}
.prog{{position:fixed;left:0;top:0;height:3px;background:var(--acc);z-index:30;width:0;transition:width .3s}}
.cover{{min-height:100svh;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;padding:40px 24px;background:var(--cbg);color:var(--cfg)}}
.cover .pub{{font:700 12px "Noto Sans KR",sans-serif;letter-spacing:.3em;opacity:.8}}.cover h1{{font-size:clamp(32px,8vw,56px);line-height:1.25;margin:16px 0 10px}}
.cover p{{opacity:.85;margin:0 0 6px}}.cover .start{{margin-top:34px;border:0;border-radius:999px;padding:15px 34px;font:800 17px "Noto Sans KR",sans-serif;background:var(--cfg);color:var(--cbg);cursor:pointer}}
.cover .dl{{margin-top:18px;display:flex;gap:10px;flex-wrap:wrap;justify-content:center}}.cover .dl a{{color:var(--cfg);font:600 13px "Noto Sans KR",sans-serif;border:1px solid currentColor;border-radius:999px;padding:7px 14px;text-decoration:none;opacity:.85}}
main{{max-width:720px;margin:0 auto;padding:78px 22px 120px}}.pg{{display:none}}.pg.on{{display:block;animation:in .35s ease}}@keyframes in{{from{{opacity:0;transform:translateY(8px)}}}}
.pg h1{{font-size:1.65em;line-height:1.3;margin:.6em 0 1em}}.pg h2{{font-size:1.2em;margin:1.8em 0 .6em}}.pg p{{margin:0 0 1em}}
blockquote{{margin:1.2em 0;padding:.4em 1em;border-left:3px solid var(--acc);color:var(--mute)}}table{{border-collapse:collapse;width:100%;font-size:.88em;margin:1em 0}}th,td{{border:1px solid var(--line);padding:.5em .6em;text-align:left}}
.term{{position:relative;margin:1.2em 0;border-radius:16px;border:1px solid var(--line);background:var(--card);cursor:pointer;min-height:96px;perspective:900px}}
.term .tf,.term .tbk{{padding:16px 18px;transition:opacity .35s}}.term .tbk{{display:none}}.term.open .tf{{display:none}}.term.open .tbk{{display:block;animation:in .35s}}
.term .tn{{font-family:"Noto Sans KR",sans-serif;font-size:1.1em}}.term .tap{{display:block;font:600 12px "Noto Sans KR",sans-serif;color:var(--acc);margin-top:6px}}
.term .td{{margin:.4em 0}}.term .tq{{color:var(--mute);font-size:.92em}}.term .tr{{font:13px "Noto Sans KR",sans-serif;color:var(--mute)}}.term .radar{{display:block;margin:6px auto 0;width:170px;height:170px}}
body.night .radar text{{fill:#e9e3d6}}body.night .radar polygon[fill="none"],body.night .radar line{{stroke:#e9e3d6}}
.quiz{{margin:1.2em 0;padding:14px 16px;border-radius:16px;background:var(--card);border:1px dashed var(--acc)}}.quiz .qq{{margin:0 0 8px;font-weight:700}}
.quiz .qb{{border:0;border-radius:999px;padding:8px 16px;background:var(--acc);color:#fff;font:700 13px "Noto Sans KR",sans-serif;cursor:pointer}}.quiz .qa{{margin:10px 0 0;font-weight:700;color:var(--acc)}}
table.cmp tbody tr{{cursor:pointer}}table.cmp tbody tr.hl{{background:color-mix(in srgb,var(--acc) 18%,transparent)}}
.fr{{color:var(--acc);font-size:.7em}}.fn{{font-size:.82em;color:var(--mute);border-top:1px solid var(--line);padding-top:.4em;margin-top:.6em}}.fn::before{{content:attr(data-fn) ". "}}
.nav{{position:fixed;inset:auto 0 0;z-index:20;display:flex;gap:8px;padding:10px 14px calc(env(safe-area-inset-bottom) + 10px);background:color-mix(in srgb,var(--bg) 92%,transparent);backdrop-filter:blur(10px);border-top:1px solid var(--line);font:700 14px "Noto Sans KR",sans-serif}}
.nav button{{flex:1;border:1px solid var(--line);background:var(--card);color:var(--ink);border-radius:14px;padding:12px;font:inherit;cursor:pointer}}.nav .mid{{flex:none;min-width:84px;color:var(--mute);display:grid;place-items:center}}
.drawer{{position:fixed;inset:0;z-index:40;background:#0008;display:none}}.drawer.on{{display:block}}
.drawer .in{{position:absolute;inset:0 18% 0 0;max-width:420px;background:var(--bg);overflow:auto;padding:calc(env(safe-area-inset-top) + 20px) 18px 30px;font-family:"Noto Sans KR",sans-serif}}
.drawer h3{{margin:0 0 10px}}.drawer ol{{list-style:none;margin:0;padding:0}}.drawer li button{{width:100%;text-align:left;border:0;background:none;color:var(--ink);padding:11px 4px;border-bottom:1px solid var(--line);font:15px "Noto Sans KR",sans-serif;cursor:pointer}}
.drawer li button em{{font-style:normal;color:var(--acc);margin-right:10px;font-weight:700}}.drawer input{{width:100%;padding:11px;border-radius:12px;border:1px solid var(--line);background:var(--card);color:var(--ink);font:15px "Noto Sans KR",sans-serif;margin:8px 0 6px}}
.hits{{font-size:13.5px}}.hits button{{display:block;width:100%;text-align:left;border:0;background:none;color:var(--ink);padding:8px 2px;border-bottom:1px dotted var(--line);cursor:pointer}}
.colophon{{font:13px/1.8 "Noto Sans KR",sans-serif;color:var(--mute);border-top:1px solid var(--line);margin-top:3em;padding-top:1em}}
</style></head><body>
<div class="prog" id="prog"></div>
<section class="cover" id="cover"><div class="pub">{e(b.get('publisher', ''))}</div><h1>{e(b['title'])}</h1><p>{e(b.get('subtitle', ''))}</p><p>{e(b['author'])} 지음</p>
<button class="start" id="start">펼치기</button><div class="dl">{''.join(dl)}</div></section>
<div class="bar" id="bar" hidden><button id="tocB" aria-label="차례">☰ 차례</button><b id="cur"></b><button id="fsB" aria-label="글자 크기">가</button><button id="ntB" aria-label="밤 화면">◐</button><button id="bmB" aria-label="책갈피">🔖</button></div>
<main id="main" hidden>{pages}<div class="colophon">{e(b['title'])} · {e(b['author'])} · {e(b.get('publisher', ''))}{(' · ISBN ' + e(b['isbn'])) if b.get('isbn') else ''}<br>앱 한 권 — 같은 원고에서 인쇄본 · 전자책 · 웹이 함께 나옵니다.</div></main>
<nav class="nav" id="nav" hidden><button id="prev">‹ 앞 장</button><span class="mid" id="pos"></span><button id="next">다음 장 ›</button></nav>
<div class="drawer" id="drawer"><div class="in"><h3>차례</h3><ol>{toc}</ol><h3 style="margin-top:22px">찾기</h3><input id="q" placeholder="낱말 찾기"><div class="hits" id="hits"></div><h3 style="margin-top:22px">책갈피</h3><div class="hits" id="bms"></div></div></div>
<script>
(function(){{
var KEY='book:'+{json.dumps(b['title'], ensure_ascii=False)},pgs=[].slice.call(document.querySelectorAll('.pg')),N=pgs.length,cur=1,$=function(i){{return document.getElementById(i)}};
function save(o){{try{{var s=JSON.parse(localStorage.getItem(KEY)||'{{}}');Object.assign(s,o);localStorage.setItem(KEY,JSON.stringify(s))}}catch(e){{}}}}
function load(){{try{{return JSON.parse(localStorage.getItem(KEY)||'{{}}')}}catch(e){{return {{}}}}}}
function open(){{$('cover').hidden=true;['bar','main','nav'].forEach(function(x){{$(x).hidden=false}})}}
function go(i){{cur=Math.max(1,Math.min(N,i));pgs.forEach(function(p,k){{p.classList.toggle('on',k===cur-1)}});$('cur').textContent=pgs[cur-1].querySelector('h1').textContent;
  $('pos').textContent=cur+' / '+N;$('prog').style.width=(cur/N*100)+'%';$('prev').disabled=cur===1;$('next').disabled=cur===N;scrollTo(0,0);save({{at:cur}});$('drawer').classList.remove('on')}}
$('start').onclick=function(){{open();go(load().at||1)}};$('prev').onclick=function(){{go(cur-1)}};$('next').onclick=function(){{go(cur+1)}};
$('tocB').onclick=function(){{$('drawer').classList.add('on');paintBm()}};$('drawer').onclick=function(e){{if(e.target===this)this.classList.remove('on')}};
document.querySelectorAll('[data-go]').forEach(function(x){{x.onclick=function(){{go(+x.dataset.go)}}}});
var sizes=[16,18,20,23],si=sizes.indexOf(load().fs||18);if(si<0)si=1;function fs(){{document.documentElement.style.setProperty('--fs',sizes[si]+'px')}}fs();
$('fsB').onclick=function(){{si=(si+1)%sizes.length;fs();save({{fs:sizes[si]}})}};
if(load().night)document.body.classList.add('night');$('ntB').onclick=function(){{document.body.classList.toggle('night');save({{night:document.body.classList.contains('night')}})}};
function paintBm(){{var b=load().bm||[];$('bms').innerHTML=b.length?b.map(function(i){{return '<button data-b="'+i+'">'+i+'장 · '+pgs[i-1].querySelector('h1').textContent+'</button>'}}).join(''):'<p>아직 없습니다. 🔖 를 누르면 지금 장이 저장됩니다.</p>';
  [].forEach.call($('bms').querySelectorAll('[data-b]'),function(x){{x.onclick=function(){{go(+x.dataset.b)}}}})}}
$('bmB').onclick=function(){{var b=load().bm||[];if(b.indexOf(cur)<0)b.push(cur);b.sort(function(a,c){{return a-c}});save({{bm:b}});$('bmB').textContent='✓';setTimeout(function(){{$('bmB').textContent='🔖'}},900)}};
$('q').oninput=function(){{var q=this.value.trim();if(q.length<2){{$('hits').innerHTML='';return}}var out=[];pgs.forEach(function(p,k){{var t=p.textContent,i=t.indexOf(q);if(i>=0)out.push('<button data-h="'+(k+1)+'"><b>'+(k+1)+'장</b> …'+t.slice(Math.max(0,i-18),i+30).replace(/</g,'&lt;')+'…</button>')}});
  $('hits').innerHTML=out.join('')||'<p>찾는 낱말이 없습니다.</p>';[].forEach.call($('hits').querySelectorAll('[data-h]'),function(x){{x.onclick=function(){{go(+x.dataset.h)}}}})}};
document.addEventListener('click',function(e){{var t=e.target.closest('.term');if(t)t.classList.toggle('open');var q=e.target.closest('.qb');if(q){{q.nextElementSibling.hidden=false;q.hidden=true}}
  var r=e.target.closest('table.cmp tbody tr');if(r)r.classList.toggle('hl')}});
document.addEventListener('keydown',function(e){{if($('main').hidden)return;if(e.key==='ArrowRight')go(cur+1);if(e.key==='ArrowLeft')go(cur-1)}});
var sx=0,sy=0;document.addEventListener('touchstart',function(e){{sx=e.touches[0].clientX;sy=e.touches[0].clientY}},{{passive:true}});
document.addEventListener('touchend',function(e){{if($('main').hidden)return;var dx=e.changedTouches[0].clientX-sx,dy=e.changedTouches[0].clientY-sy;if(Math.abs(dx)>70&&Math.abs(dx)>Math.abs(dy)*1.5)go(cur+(dx<0?1:-1))}},{{passive:true}});
if(load().at){{$('start').textContent='이어 읽기 ('+load().at+'장)'}}
}})();
</script></body></html>"""
    (out / "index.html").write_text(doc, encoding="utf-8")
    return out


if __name__ == "__main__":
    a = argparse.ArgumentParser(); a.add_argument("book"); a.add_argument("out"); a.add_argument("--pdf"); a.add_argument("--epub")
    o = a.parse_args()
    print(build(Path(o.book), Path(o.out), Path(o.pdf) if o.pdf else None, Path(o.epub) if o.epub else None))
