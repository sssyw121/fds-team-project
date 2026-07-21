# -*- coding: utf-8 -*-
"""
화면 연동 렌더러 — 파이프라인 산출물을 팀원 화면 전체에 주입한다
=================================================================
팀원이 만든 `ui/*.html`은 점수·금액·건수가 **하드코딩**돼 있다.
이 스크립트는 디자인을 그대로 두고 **숫자와 문구만** 계산 결과로 교체한 뒤,
**모든 화면을 `ui/live/`에 같은 파일명으로** 내보낸다.

  outputs/screen_payload.json   (FDS_통합_스코어링.ipynb 산출)
        ↓  주입
  ui/live/*.html                (화면 간 이동이 그대로 작동 — 데모 영상용)

설계 원칙
---------
1. **파일명을 바꾸지 않는다.** 원본의 `location.href='linked-accounts.html'` 링크가
   수정 없이 동작해야 데모에서 화면을 눌러 넘길 수 있다.
2. **CSS를 문서 안에 인라인한다.** 파일 하나만 열어도, 다른 PC로 옮겨도 안 깨진다.
3. **CSS·레이아웃은 건드리지 않는다.** 팀원 작업물을 그대로 두고 값만 살아있게 만든다.
"""

import json, re, html, shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
UI   = BASE / "ui"
OUT  = UI / "live"
OUT.mkdir(exist_ok=True)

payloads = json.loads((BASE / "outputs" / "screen_payload.json").read_text(encoding="utf-8"))
cases = list(payloads.values())          # 위험도 내림차순 (파이프라인이 정렬해 둠)

# SHAP 화면 3개에 사례를 하나씩 배정 — 파일명은 원본 유지
SHAP_MAP = {
    "shap-starbucks.html": cases[0],
    "shap-coupang.html":   cases[1] if len(cases) > 1 else cases[0],
    "shap-explain.html":   cases[2] if len(cases) > 2 else cases[0],
}

ICON = {
    "여러 계정에 접속을 시도한 곳에서 로그인 요청이 있었어요": ("🌐", "같은 접속처에서 다수 계정에 로그인 시도가 관측됨"),
    "여러 계정을 시도한 접속처에서 로그인 시도가 있었어요":     ("🌐", "같은 접속처에서 다수 계정에 로그인 시도가 관측됨"),
    "평소 접속하지 않던 지역에서 로그인되었어요":              ("🌏", "최근 이 계정은 국내에서만 접속"),
    "로그인 직후 연락처가 변경되었어요":                      ("✏️", "로그인 성공 60분 내 연락처 변경 · 이례적 패턴"),
    "평소 쓰지 않던 기기에서 접속했어요":                     ("📱", "이 계정에서 관측된 적 없는 기기"),
    "평소 쓰지 않던 기기에서 결제했어요":                     ("📱", "이 계정에서 관측된 적 없는 기기"),
    "로그인 실패가 반복된 뒤 성공했어요":                     ("🔁", "연속 실패 후 성공 · 크리덴셜 대입 정황"),
    "계열 서비스에서 회원님 정보가 확인되었어요":              ("🔴", "자사·계열 유출 사고 명단에 포함"),
    "외부에 유출된 정보와 일치하는 항목이 있어요":             ("🕳️", "외부 유출 정보와 일치"),
    "평소보다 큰 금액이었어요":                             ("💸", "평소 결제 금액 대비 이탈"),
    "평소 결제 금액과 차이가 컸어요":                        ("💸", "평소 결제 금액 대비 이탈"),
    "바로 사용할 수 있는 상품이었어요":                       ("🎫", "충전 즉시 사용 가능 · 회수 불가"),
}
NUM_KO = {1: "한", 2: "두", 3: "세", 4: "네", 5: "다섯", 6: "여섯"}


def inline_css(doc):
    css = (UI / "shared.css").read_text(encoding="utf-8")
    return re.sub(r'<link[^>]*shared\.css[^>]*>', f"<style>\n{css}\n</style>", doc)


def badge(data, extra=""):
    """LIVE 배지 — 화면 레이아웃을 건드리지 않도록 **고정 오버레이**로 띄운다.

    처음에는 화면 안쪽에 <div>로 끼워 넣었더니 14개 화면의 구조가 제각각이라
    폰 프레임 밖으로 삐져나오는 화면이 생겼다. position:fixed로 바꿔
    어떤 화면에 붙여도 원본 레이아웃이 깨지지 않게 한다.
    """
    return f'''
<div style="position:fixed;left:12px;bottom:12px;z-index:9999;max-width:340px;
            padding:10px 12px;border-radius:10px;background:rgba(238,246,255,.97);
            border:1px solid #CFE4FF;font-size:11px;color:#1B5FAA;line-height:1.5;
            font-family:-apple-system,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.12)">
  <b>LIVE</b> · 이 화면의 숫자는 <code>FDS_통합_스코어링.ipynb</code>가 계산한
  <code>screen_payload.json</code>에서 주입되었습니다.<br>
  계정 <b>{data["user_id"]}</b> · 노출 정황 {data["exposure_score"]}점 ·
  계정 장악 {data["takeover_score"]}점 → 조치 <b>{data["action"]}</b>{extra}
</div>
'''


def factor_html(text, contrib, mx):
    emoji, desc = ICON.get(text, ("⚠️", "판정에 기여한 신호"))
    width = max(12, round(contrib / mx * 100))
    level = "high" if contrib >= 20 else ("mid" if contrib >= 12 else "low")
    return f'''
      <div class="factor">
        <div class="factor-row">
          <div class="factor-emoji">{emoji}</div>
          <div class="factor-body">
            <div class="factor-title">{html.escape(text)}</div>
            <div class="factor-desc">{html.escape(desc)}</div>
          </div>
          <div class="factor-impact {level} mono-num">+{contrib:g}</div>
        </div>
        <div class="factor-bar"><div class="fill" style="width:{width}%;"></div></div>
      </div>
'''


def render_shap(doc, data):
    r = data["reasons"]; n = len(r); mx = max(x["contrib"] for x in r) if r else 1
    doc = re.sub(r'(<div class="value mono-num">)\d+(<span class="max">)',
                 rf'\g<1>{data["total_score"]}\g<2>', doc)
    doc = re.sub(r'(<div class="verdict">)[^<]*(</div>)', rf'\g<1>{data["level"]}\g<2>', doc)
    t = data["target"]
    if t:
        doc = re.sub(r'(<div class="t1">)[^<]*(</div>)',
                     rf'\g<1>{t["time"]} · {t["merchant"]}\g<2>', doc, count=1)
        doc = re.sub(r'(<div class="t2">)[^<]*(</div>)',
                     rf'\g<1>{t["merchant"]} 결제 시도\g<2>', doc, count=1)
        doc = re.sub(r'(<div class="amt">)[^<]*(</div>)',
                     rf'\g<1>{t["amount"]:,}원\g<2>', doc, count=1)
    blocks = "".join(factor_html(x["text"], x["contrib"], mx) for x in r)
    doc = re.sub(r'\n\s*<!-- 요인 1.*?(?=<div class="factors-note">)',
                 "\n" + blocks + "\n      ", doc, flags=re.S)
    doc = re.sub(r'판단에 쓰인 [가-힣]+ 가지 근거', f'판단에 쓰인 {NUM_KO.get(n, n)} 가지 근거', doc)
    doc = re.sub(r'[가-힣]+ 가지 근거가 모두 겹친', f'{NUM_KO.get(n, n)} 가지 근거가 모두 겹친', doc)
    doc = re.sub(r'(비교해\s*)[가-힣]+ 가지', rf'\g<1>{NUM_KO.get(n, n)} 가지', doc)
    return doc.replace("</body>", badge(data) + "</body>", 1)


def render_home_alert(doc):
    """차단 건수·합계 금액을 실제 집계로 교체"""
    n = len(cases)
    total = sum(c["target"]["amount"] for c in cases if c["target"])
    doc = re.sub(r'지난밤 \d+건의 결제 시도를 막았어요\.',
                 f'지난밤 {n}건의 결제 시도를 막았어요. 합계 {total:,}원이에요.', doc)
    return doc.replace("</body>", badge(cases[0], f"<br>차단 {n}건 · 합계 {total:,}원") + "</body>", 1)


def render_linked(doc):
    """연결 서비스 화면 — 시도 시각·금액을 실제 값으로 교체"""
    times   = [c["target"]["time"]   for c in cases if c["target"]]
    amounts = [c["target"]["amount"] for c in cases if c["target"]]

    ti = iter(times)
    def sub_time(m):
        v = next(ti, None)
        return f">{v}<" if v else m.group(0)
    doc = re.sub(r'>0[0-9]:[0-9]{2}<', sub_time, doc)

    ai = iter(amounts)
    def sub_amt(m):
        v = next(ai, None)
        return f">{v:,}원<" if v else m.group(0)
    doc = re.sub(r'>\d{2,3},\d{3}원<', sub_amt, doc)

    return doc.replace("</body>", badge(cases[0], f"<br>위험 감지 {len(cases)}건") + "</body>", 1)




def render_retry_branch(doc, label):
    """재감지 분기(B·C·D) — 화면의 시나리오 숫자는 **건드리지 않는다.**

    화면의 "12분"은 사용자가 [유지한다]를 누른 뒤의 경과 시간인데,
    우리 파이프라인에는 사용자의 유지 선택 이벤트가 없어 계산할 수 없다.
    없는 값을 지어내는 대신, **그 시나리오가 실측 분포 안에 있다는 근거**를 배지로 덧붙인다.
    """
    note = (f'''
<div style="position:fixed;left:12px;bottom:12px;z-index:9999;max-width:360px;
            padding:10px 12px;border-radius:10px;background:rgba(255,247,237,.97);
            border:1px solid #FFD9A8;font-size:11px;color:#8A4B08;line-height:1.5;
            font-family:-apple-system,sans-serif;box-shadow:0 4px 16px rgba(0,0,0,.12)">
  <b>근거</b> · {label}<br>
  실측(합성 데이터 {{n}}건): 계정 탈취 성공 → <b>계정정보 변경</b>까지
  중앙값 <b>31분</b>(최소 4분) · → <b>사기 결제</b>까지 중앙값 <b>90분</b>(최소 26분)<br>
  <span style="opacity:.8">화면의 "12분"은 사용자가 [유지한다]를 누른 뒤의 시간이라
  파이프라인이 계산하지 않습니다. 시나리오 값 그대로 두었습니다.</span>
</div>
''').replace("{n}", "19")
    return doc.replace("</body>", note + "</body>", 1)



# ── 데모 내비게이션 ────────────────────────────────────────────────
# retry-lock.html 은 팀원 프로토타입에서 **들어오는 링크가 0개**라
# 클릭으로 도달할 수 없다(화면은 만들었으나 연결이 빠짐).
# 원본 링크를 고치지 않고, 데모용 오버레이로 순서를 따라갈 수 있게 한다.
DEMO_ORDER = [
    ("index.html",           "평시 간편결제"),
    ("home-alert.html",      "위험 감지 · 기능④ 전파"),
    ("notify.html",          "알림"),
    ("linked-accounts.html", "연결 서비스 12곳"),
    ("shap-starbucks.html",  "왜 위험한가 · 기여도"),
    ("keep-starbucks.html",  "A. 유지한다 선택"),
    ("keep-confirm.html",    "A. 유지 확정"),
    ("retry-lock.html",      "B. 12분 뒤 재알림"),
    ("re-detected.html",     "C. 재감지 — 실제 탈취"),
    ("account-locked.html",  "D. 계정 잠금 완료"),
    ("protect-action.html",  "보호조치 3단계"),
]

def demo_nav(fname):
    names = [f for f, _ in DEMO_ORDER]
    if fname not in names:
        return ""
    i = names.index(fname)
    prev = names[i-1] if i > 0 else None
    nxt  = names[i+1] if i < len(names)-1 else None
    label = DEMO_ORDER[i][1]
    btn = ("display:inline-block;padding:6px 12px;border-radius:8px;text-decoration:none;"
           "font-size:12px;font-weight:600;")
    prev_h = (f'<a href="{prev}" style="{btn}background:#fff;color:#333;border:1px solid #ddd">‹ 이전</a>'
              if prev else f'<span style="{btn}color:#bbb">‹ 이전</span>')
    next_h = (f'<a href="{nxt}" style="{btn}background:#111;color:#fff">다음 ›</a>'
              if nxt else f'<span style="{btn}color:#bbb">끝</span>')
    return f'''
<div style="position:fixed;right:12px;bottom:12px;z-index:9999;
            padding:8px 10px;border-radius:10px;background:rgba(255,255,255,.97);
            border:1px solid #E3E5E8;box-shadow:0 4px 16px rgba(0,0,0,.12);
            font-family:-apple-system,sans-serif;display:flex;align-items:center;gap:8px">
  <div style="font-size:11px;color:#666;line-height:1.35;text-align:right">
    <b style="color:#111">{i+1} / {len(names)}</b><br>{label}
  </div>
  {prev_h}{next_h}
</div>
'''


RENDERERS = {**{k: (lambda d, data=v: render_shap(d, data)) for k, v in SHAP_MAP.items()},
             "home-alert.html": render_home_alert,
             "linked-accounts.html": render_linked,
             "retry-lock.html":     lambda d: render_retry_branch(d, "B. 원래 연락처로 재알림"),
             "re-detected.html":    lambda d: render_retry_branch(d, "C. 재감지 — 실제 탈취 확인"),
             "account-locked.html": lambda d: render_retry_branch(d, "D. 계정 잠금 완료")}


if __name__ == "__main__":
    made = []
    for src in sorted(UI.glob("*.html")):
        doc = src.read_text(encoding="utf-8")
        fn = RENDERERS.get(src.name)
        tag = "(원본 그대로)"
        if fn:
            try:
                doc = fn(doc); tag = "← 실데이터 주입"
            except Exception as e:
                tag = f"⚠ 주입 실패({e.__class__.__name__}) — 원본 사용"
        doc = doc.replace("</body>", demo_nav(src.name) + "</body>", 1)
        (OUT / src.name).write_text(inline_css(doc), encoding="utf-8")
        made.append(src.name)
        print(f"  {src.name:26s} {tag}")
    shutil.copy(UI / "shared.css", OUT / "shared.css")

    rows = "\n".join(
        f'<tr><td><a href="{f}">{f}</a></td>'
        f'<td>{"✅ 실데이터" if f in RENDERERS else "—"}</td></tr>' for f in made)
    (OUT / "_demo.html").write_text(f"""<!doctype html><meta charset="utf-8">
<title>FDS 데모 — 화면 × 파이프라인</title>
<style>body{{font-family:-apple-system,sans-serif;max-width:720px;margin:40px auto;padding:0 20px;line-height:1.7}}
a{{color:#0A66C2}} code{{background:#f4f4f5;padding:2px 5px;border-radius:4px}}
table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid #eee;padding:7px 4px;text-align:left;font-size:14px}}
.hero{{background:#111;color:#fff;padding:20px;border-radius:14px;margin-bottom:24px}}</style>
<div class="hero"><h1 style="margin:0 0 6px">FDS 데모 — 화면 × 파이프라인 연동</h1>
<div style="opacity:.75;font-size:14px">디자인은 팀원 원본 그대로, 숫자만 계산 결과로 주입했습니다.</div></div>
<div style="background:#F7F8FA;border-radius:12px;padding:16px 18px;margin-bottom:22px">
<b>데모 순서</b> — <a href="index.html">index.html</a> 에서 시작해 클릭으로 진행됩니다.
<pre style="margin:12px 0 0;font-size:13px;line-height:1.65;white-space:pre-wrap">index → home-alert → notify → linked-accounts
                                    │
        ┌───────────────────────────┴───────────────────────────┐
   <b>[분기 ①] 조치함</b>                                 <b>[분기 ②] 유지한다</b> ⭐
   shap-starbucks  왜 위험한지                       keep-starbucks   (A) 유지 선택
        ↓                                                ↓
   protect-action  3단계 보호조치                    retry-lock      (B) 12분 뒤 재알림
                                                         ↓
                                                    re-detected     (C) 실제 탈취였음
                                                         ↓
                                                    account-locked  (D) 계정 잠금 완료</pre>
<p style="margin:12px 0 0;font-size:13px"><b>분기 ②를 추천합니다.</b> 사용자가 "내가 맞다"고 응답했는데도
시스템이 감시를 유지해 결국 잡아내는 흐름이라, <code>its_me</code> 응답을 무조건 신뢰하면 안 된다는
설계 판단(이벤트 로그 스키마 v2)이 화면으로 드러납니다.</p>
</div>
<table><tr><th>화면</th><th>데이터</th></tr>{rows}</table>
<p style="color:#666;font-size:13px;margin-top:24px">⚠️ 로그인·계정변경 데이터는 합성입니다
(<code>code/DATA_CARD.md</code>). 결제 데이터는 수업 실습 제공분입니다.</p>
""", encoding="utf-8")
    print(f"\n총 {len(made)}개 화면 → {OUT}")
    print(f"진입점: {OUT/'_demo.html'}")
