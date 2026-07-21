# -*- coding: utf-8 -*-
"""
FDS 데모용 합성 이벤트 생성기 — 로그인 층 / 계정 변경 층
========================================================
수업 실습 데이터 `transactions.csv`(결제 층)에는 로그인·계정변경 이벤트가 없다.
기능②(계정 장악 감지)를 시연하려면 그 두 층이 필요하므로 **합성**한다.

⚠️ 이 파일이 만드는 데이터는 전부 합성이다. 실측 근거로 쓰면 안 된다.
   합성 규칙은 RBA 실측값(공격 IP 계정수 중앙값 4 / 정상 1 등)을 참고해 정했다.

설계 원칙 (aryan208 데이터셋에서 배운 교훈)
--------------------------------------------
"라벨이 있다"와 "라벨이 신호를 담고 있다"는 다르다.
너무 쉽게 풀리는 합성 데이터는 아무것도 증명하지 못하므로, 의도적으로
**정상인데 위험해 보이는 사례**를 충분히 섞는다.

  · 새 폰을 사서 기기를 바꾼 뒤 이메일을 바꾸는 정상 사용자
  · 출장·여행으로 해외에서 로그인하는 정상 사용자
  · 회사·카페 공용 와이파이처럼 여러 계정이 함께 쓰는 정상 IP
  · 계정을 뚫었지만 결제까지 가지 않은 공격 (기능②의 오탐이 아니라 정탐인데 결제가 없는 케이스)

출력
----
  login_events.csv          로그인 시도 1건 = 1행
  account_change_events.csv 계정 정보 변경 1건 = 1행
"""

import numpy as np
import pandas as pd
from pathlib import Path

SEED = 52
rng = np.random.default_rng(SEED)

BASE = Path(__file__).parent
TX_PATH = BASE / "transactions.csv"

# ============================================================
# 0. 결제 데이터에서 사용자 프로필 추출
# ============================================================
tx = pd.read_csv(TX_PATH, encoding="utf-8-sig")
tx["transaction_time"] = pd.to_datetime(tx["transaction_time"])

T_START, T_END = tx.transaction_time.min(), tx.transaction_time.max()
users = sorted(tx.user_id.unique())
n_users = len(users)

# 사용자별 주 거주지 = 해외를 뺀 최빈 location
home = (tx[tx.location != "해외"]
        .groupby("user_id")["location"]
        .agg(lambda s: s.mode().iloc[0] if len(s.mode()) else "서울"))
home = home.reindex(users).fillna("서울")

# 사기 거래를 가진 사용자 = 실제로 결제까지 간 피해자
fraud_tx = tx[tx.is_fraud == 1].copy()
victim_users = fraud_tx.user_id.unique().tolist()

print(f"기간   : {T_START} ~ {T_END}")
print(f"사용자 : {n_users}명 | 사기 거래 피해자: {len(victim_users)}명")

# ============================================================
# 1. 사용자 프로필 — 기기 / IP / 성향
# ============================================================
OS_POOL = ["iOS 17.4", "iOS 16.6", "Android 14", "Android 13", "Windows 11", "macOS 14"]

profile = {}
for i, u in enumerate(users):
    n_dev = rng.choice([1, 2], p=[0.7, 0.3])          # 주 기기 1~2대
    profile[u] = {
        "home": home[u],
        "devices": [f"DEV-{u[1:]}-{k}" for k in range(n_dev)],
        "os": list(rng.choice(OS_POOL, size=n_dev, replace=False)),
        "ip": f"211.{rng.integers(0,256)}.{rng.integers(0,256)}.{rng.integers(1,255)}",
        "traveler": rng.random() < 0.08,               # 8%는 해외 출장·여행이 잦음
        "night_owl": rng.random() < 0.15,              # 15%는 심야 활동
    }

# 공용 IP (회사·카페·통신사 NAT) — 정상인데 여러 계정이 함께 쓴다 = E3의 오탐 재료
# 이게 충분히 많아야 "계정 수가 많다 = 공격"이라는 단순 판별이 통하지 않는다
n_shared = 30
shared_ips = [f"121.{rng.integers(0,256)}.{rng.integers(0,256)}.{rng.integers(1,255)}"
              for _ in range(n_shared)]
shared_members = {ip: list(rng.choice(users, size=rng.integers(4, 26), replace=False))
                  for ip in shared_ips}
user_shared = {}
for ip, members in shared_members.items():
    for u in members:
        user_shared.setdefault(u, []).append(ip)

rows = []
def add_login(user, ts, ip, device, os_, country, success, is_attack_ip):
    rows.append(dict(user_id=user, login_time=ts, ip_addr=ip, device_id=device,
                     os_version=os_, country=country,
                     login_success=int(success), is_attack_ip=int(is_attack_ip)))

# ============================================================
# 2. 정상 로그인 생성
# ============================================================
span_min = int((T_END - T_START).total_seconds() // 60)

for u in users:
    p = profile[u]
    n_tx = int((tx.user_id == u).sum())
    n_login = max(4, int(rng.poisson(n_tx * 3)))       # 결제 1건당 로그인 약 3회

    for _ in range(n_login):
        ts = T_START + pd.Timedelta(minutes=int(rng.integers(0, span_min)))
        # 심야형이 아니면 새벽 로그인을 낮 시간으로 되돌린다
        if not p["night_owl"] and ts.hour < 6:
            ts += pd.Timedelta(hours=int(rng.integers(7, 16)))
        d_idx = rng.integers(0, len(p["devices"]))
        device, os_ = p["devices"][d_idx], p["os"][d_idx]

        # 기기: 90% 주 기기, 8% 공용 와이파이에서 주 기기, 2% 새 기기(기변)
        r = rng.random()
        if r < 0.72:
            ip = p["ip"]
        elif r < 0.98 and u in user_shared:
            ip = rng.choice(user_shared[u])
        else:
            ip = p["ip"]
            device, os_ = f"DEV-{u[1:]}-new", str(rng.choice(OS_POOL))   # 기기 변경

        country = "해외" if (p["traveler"] and rng.random() < 0.25) else "KR"
        success = rng.random() < 0.97                                     # 3%는 오타 등 실패
        add_login(u, ts, ip, device, os_, country, success, False)

# ============================================================
# 3. 크리덴셜 스터핑 공격 생성
# ============================================================
# RBA 실측 참고: 공격 IP는 판정 시점 누적 기준 **중앙값 4개** 계정, 최대 수백 개.
# 즉 대부분의 공격 IP는 조용하고, 소수만 시끄럽다(멱법칙).
# 이 분포를 지켜야 "계정 수가 많다"만으로 공격을 가려낼 수 없게 되어 현실적이다.
N_ATTACK_IP = 260
attack_ips = [f"45.{rng.integers(0,256)}.{rng.integers(0,256)}.{rng.integers(1,255)}"
              for _ in range(N_ATTACK_IP)]

# 피해자(결제까지 간 12명)는 반드시 뚫린다
compromised = set(victim_users)
# 뚫렸지만 결제까지 가지 않은 계정도 만든다 (공격자가 수익화 실패)
extra_pool = [u for u in users if u not in compromised]
compromised |= set(rng.choice(extra_pool, size=13, replace=False))
compromised = sorted(compromised)

# 각 공격 IP가 두드릴 계정 배정 — 멱법칙: 대부분 조용, 소수만 시끄럽다
attack_targets = {}
for i, ip in enumerate(attack_ips):
    if i < 3:                                   # 시끄러운 공격 IP 3개 (봇넷 노드)
        k = int(rng.integers(25, 55))
    else:                                       # 대다수는 저강도 분산 공격 (low-and-slow)
        k = int(max(2, rng.pareto(2.2) * 2.5 + 2))
    attack_targets[ip] = list(rng.choice(users, size=min(k, n_users), replace=False))

# 뚫린 계정은 반드시 어떤 공격 IP의 타깃에 포함시킨다
for u in compromised:
    ip = attack_ips[rng.integers(0, N_ATTACK_IP)]
    if u not in attack_targets[ip]:
        attack_targets[ip].append(u)

ato_login = {}         # user -> ATO 성공 시각
ato_country_map = {}   # user -> ATO 로그인 국가 (국내 프록시 경유 여부)
for ip, targets in attack_targets.items():
    # 한 공격 IP의 공격은 특정 시간대에 몰린다 (버스트)
    burst_start = T_START + pd.Timedelta(minutes=int(rng.integers(0, span_min - 2880)))
    for u in targets:
        n_try = int(rng.integers(1, 4))
        for _ in range(n_try):
            ts = burst_start + pd.Timedelta(minutes=int(rng.integers(0, 2880)))
            add_login(u, ts, ip, f"BOT-{rng.integers(1000,9999)}",
                      str(rng.choice(OS_POOL)), "해외", False, True)   # 대부분 실패

        if u in compromised and u not in ato_login:
            # 피해자는 사기 결제 직전에 뚫려야 인과가 맞는다
            if u in victim_users:
                first_fraud = fraud_tx[fraud_tx.user_id == u].transaction_time.min()
                ts = first_fraud - pd.Timedelta(minutes=int(rng.integers(8, 180)))
            else:
                ts = burst_start + pd.Timedelta(minutes=int(rng.integers(0, 2880)))
            # ★ 공격자의 20%는 국내 프록시를 경유한다 (PRD 부록 B의 우회 시나리오).
            #   이들은 '해외' 조건 룰에 걸리지 않아, 재현율의 상한을 만든다.
            ato_country = "KR" if rng.random() < 0.20 else "해외"
            add_login(u, ts, ip, f"BOT-{rng.integers(1000,9999)}",
                      str(rng.choice(OS_POOL)), ato_country, True, True)   # 성공 = ATO
            ato_login[u] = ts
            ato_country_map[u] = ato_country

# ============================================================
# 4. 계정 정보 변경 이벤트
# ============================================================
chg = []
def add_change(user, ts, ctype, device, ip, country):
    chg.append(dict(user_id=user, change_time=ts, change_type=ctype,
                    device_id=device, ip_addr=ip, country=country))

CHANGE_TYPES = ["email", "phone", "password"]

# (a) 공격자: ATO 직후 알림 채널을 끊는다 — 전부는 아니다(일부는 바로 결제로 감)
for u, t_ato in ato_login.items():
    if rng.random() < 0.72:
        ts = t_ato + pd.Timedelta(minutes=int(rng.integers(1, 55)))
        ctype = str(rng.choice(["email", "phone"], p=[0.65, 0.35]))
        add_change(u, ts, ctype, f"BOT-{rng.integers(1000,9999)}",
                   [r["ip_addr"] for r in rows if r["user_id"] == u][-1],
                   ato_country_map[u])

# (b) 정상: 기기를 바꾼 뒤 연락처를 바꾸는 사람들 ← 기능②의 핵심 오탐 재료
#     이 중 일부는 **해외에서** 바꾼다 (여행 중 분실·기변, 해외 체류, 이민).
#     드물지만 반드시 존재하며, 이게 없으면 "신규기기+해외 = 공격"이 100% 맞아떨어져
#     합성 데이터가 비현실적으로 쉬워진다.
normal_pool = [u for u in users if u not in ato_login]
for u in rng.choice(normal_pool, size=34, replace=False):
    p = profile[u]
    ts = T_START + pd.Timedelta(minutes=int(rng.integers(0, span_min)))
    abroad = rng.random() < 0.34            # 정상 기변 중 약 1/3은 해외에서
    country = "해외" if abroad else "KR"
    add_change(u, ts, str(rng.choice(CHANGE_TYPES)), f"DEV-{u[1:]}-new", p["ip"], country)
    # 변경 직전에 새 기기 로그인을 남겨 인과를 맞춘다
    add_login(u, ts - pd.Timedelta(minutes=int(rng.integers(2, 40))), p["ip"],
              f"DEV-{u[1:]}-new", str(rng.choice(OS_POOL)), country, True, False)

# (c) 정상: 평범한 비밀번호 주기 변경 (기존 기기, 국내)
#     이건 '60분 내 변경' 룰에는 걸리지만 '신규기기' 조건에서 걸러져야 한다.
for u in rng.choice(normal_pool, size=40, replace=False):
    p = profile[u]
    ts = T_START + pd.Timedelta(minutes=int(rng.integers(0, span_min)))
    add_change(u, ts, "password", p["devices"][0], p["ip"], "KR")
    add_login(u, ts - pd.Timedelta(minutes=int(rng.integers(2, 50))), p["ip"],
              p["devices"][0], p["os"][0], "KR", True, False)

# ============================================================
# 5. 저장
# ============================================================
login = pd.DataFrame(rows).sort_values("login_time").reset_index(drop=True)
login["login_id"] = [f"L{i:06d}" for i in range(1, len(login) + 1)]
login = login[["login_id", "user_id", "login_time", "ip_addr", "device_id",
               "os_version", "country", "login_success", "is_attack_ip"]]

change = pd.DataFrame(chg).sort_values("change_time").reset_index(drop=True)
change["change_id"] = [f"C{i:05d}" for i in range(1, len(change) + 1)]
change = change[["change_id", "user_id", "change_time", "change_type",
                 "device_id", "ip_addr", "country"]]

# 사후 라벨 (평가 전용 — 모델 입력 금지)
login["is_account_takeover"] = [
    int(r.user_id in ato_login and r.login_time == ato_login[r.user_id]
        and r.login_success == 1) for r in login.itertuples()]

login.to_csv(BASE / "login_events.csv", index=False, encoding="utf-8-sig")
change.to_csv(BASE / "account_change_events.csv", index=False, encoding="utf-8-sig")

print(f"\nlogin_events.csv          {login.shape}  (ATO {int(login.is_account_takeover.sum())}건)")
print(f"account_change_events.csv {change.shape}")
print(f"뚫린 계정 {len(compromised)}명 = 결제까지 간 피해자 {len(victim_users)}명 + 수익화 실패 {len(compromised)-len(victim_users)}명")
