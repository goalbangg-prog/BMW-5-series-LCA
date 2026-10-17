"""
BMW 5시리즈 전과정평가(LCA) 모델 — 한국 주행 조건 + Scope 3 + 회피배출
=====================================================================================

목표    : 같은 5시리즈 차체에서 동력(가솔린 / 플러그인 하이브리드 / 전기)만 다를 때
          한국에서 탔을 때의 생애주기 온실가스(tCO2e)를 비교하고, 그 결과를
          (1) BMW 코리아의 Scope 3 항목으로 옮기고 (2) 회피배출 주장 규칙으로 검증한다.
기능단위: 승용차 1대가 200,000 km 주행 (1 km당 값 함께 보고)
기준흐름: 차 1대 + 기능단위를 채우는 데 필요한 휘발유(L)·전기(kWh) (reference_flows())

데이터와 방법
 1. 배경 데이터: 한국환경산업기술원 국가 LCI DB 데이터셋(soda4LCA)의 대기 배출 원소 흐름을
    IPCC 6차 보고서(AR6) GWP100으로 특성화 (ISO 14067). 2차 보고서(SAR)·영국 DESNZ 2026은 비교용
 2. 휘발유 연소: 2006 IPCC 기본값 + 국내 순발열량
 3. 전력: 국가 LCI DB 소비 믹스 데이터셋(2021년 자료)을 그대로 기준값으로 쓴다.
    다른 연도는 같은 값에 발전소 직접배출의 변화 비율(2021년 국가 전력배출계수 대비)만 곱한다
 4. Scope 3(BMW 코리아 기준, 판매 대수 × 1대 값)와 WBCSD 회피배출

실행: python3 analysis/lca_model.py  → outputs/
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA, OUT = ROOT / "data", ROOT / "outputs"
OUT.mkdir(exist_ok=True)

F = json.loads((DATA / "factors.json").read_text(encoding="utf-8"))
veh = pd.read_csv(DATA / "vehicles.csv")
V = {r.id: r for r in veh.itertuples(index=False)}
KEI = F["keiti_lcidb"]
DS = KEI["datasets"]


def isnum(x) -> bool:
    return x is not None and x == x and x != ""


# ---------------------------------------------------------------------------
# 1. 연소 배출계수 (IPCC 2006 + 국내 순발열량 + GWP)
# ---------------------------------------------------------------------------
def co2e_per_TJ(ef: dict, gwp: dict) -> float:
    return ef["CO2"] + gwp["CH4"] * ef["CH4"] + gwp["N2O"] * ef["N2O"]


# 기본은 ISO 14067이 요구하는 최신 IPCC 값(AR6 GWP100). SAR(국내 배출권거래제 지침)은 비교용
GWP_AR6 = {"CH4": F["gwp"]["CH4_fossil"], "N2O": F["gwp"]["N2O"], "key": "ar6"}
GWP_SAR = {"CH4": F["gwp"]["alt_SAR"]["CH4"], "N2O": F["gwp"]["alt_SAR"]["N2O"], "key": "sar"}
GWP_AR5 = {**F["gwp"]["alt_AR5"], "key": "ar5"}
NCV = F["ncv"]
IP = F["ipcc2006"]


def gasoline_combustion(gwp=GWP_AR6, row="gasoline_road_kg_per_TJ") -> float:
    """kgCO2e/L"""
    return NCV["gasoline_MJ_per_L"] * 1e-6 * co2e_per_TJ(IP[row], gwp)


def ds(name, gwp=GWP_AR6, longterm=False):
    """국가 LCI DB 데이터셋의 기후변화 값 (대기 배출 원소 흐름을 다시 특성화한 값)"""
    k = "sar" if gwp["key"] == "sar" else "ar6"
    return DS[name][f"{k}_short"] + (DS[name][f"{k}_longterm"] if longterm else 0.0)


def gasoline_upstream(src="lcidb", density=None, gwp=GWP_AR6, longterm=False) -> float:
    """휘발유 생산(원유 채굴~정제) kgCO2e/L"""
    if src == "desnz":
        return NCV["gasoline_MJ_per_L"] * F["upstream_desnz2026_g_per_MJ_ncv"]["petrol"] / 1000
    return ds("gasoline", gwp, longterm) * (density or KEI["gasoline_density_kg_per_L"])


# ---------------------------------------------------------------------------
# 2. 전력 배출계수 (감소 비율 계산용 IPCC 2006 발전 모델 포함)
# ---------------------------------------------------------------------------
G = F["grid"]
EFF = G["efficiency_2023_hhv_sendout"]
FUEL = {
    "coal": dict(eta=EFF["coal"], n2g=NCV["coal_MJ_per_kg"] / NCV["coal_GCV_MJ_per_kg"], ef=IP["coal_energy_kg_per_TJ"],
                 up=F["upstream_desnz2026_g_per_MJ_ncv"]["coal"]),
    "gas": dict(eta=EFF["lng_cc"], n2g=NCV["lng_MJ_per_kg"] / NCV["lng_GCV_MJ_per_kg"], ef=IP["gas_energy_kg_per_TJ"],
                up=F["upstream_desnz2026_g_per_MJ_ncv"]["lng"]),
    "oil": dict(eta=EFF["oil"], n2g=NCV["bc_oil_MJ_per_L"] / NCV["bc_oil_GCV_MJ_per_L"], ef=IP["oil_energy_kg_per_TJ"],
                up=F["upstream_desnz2026_g_per_MJ_ncv"]["oil"]),
}


def fuel_MJ_per_kWh(f):
    return 3.6 / FUEL[f]["eta"] * FUEL[f]["n2g"]


def direct_kg_per_kWh(f, gwp=GWP_AR6):
    return fuel_MJ_per_kWh(f) * co2e_per_TJ(FUEL[f]["ef"], gwp) * 1e-6


def upstream_kg_per_kWh(f, override=None):
    return fuel_MJ_per_kWh(f) * (override[f] if override else FUEL[f]["up"]) / 1000


g23 = G["gen_2023_GWh"]
SHARE = {2023: {"coal": (g23["coal"] + g23["igcc"]) / g23["total"],
                "gas": (g23["lng"] + g23["fuel_cell"] + g23["other"]) / g23["total"],
                "oil": g23["oil"] / g23["total"]}}
for y, mix in G["plan11_TWh"].items():
    if not y.isdigit():
        continue
    tot = sum(mix.values())
    SHARE[int(y)] = {"coal": mix["coal"] / tot, "gas": (mix["lng"] + mix["other"]) / tot, "oil": 0.0}

RAW_DIRECT_2023 = sum(SHARE[2023][f] * direct_kg_per_kWh(f, GWP_SAR) for f in FUEL)
K_CAL = G["official_2023_t_per_MWh"] / RAW_DIRECT_2023


def grid_ipcc(year=2023, gwp=GWP_AR6, override=None, upstream=True) -> float:
    s = SHARE[year]
    d = sum(s[f] * direct_kg_per_kWh(f, gwp) for f in FUEL)
    u = sum(s[f] * upstream_kg_per_kWh(f, override) for f in FUEL) if upstream else 0.0
    return K_CAL * (d + u)


# 전력 계수는 한 가지 방법으로 통일:
#   기준 계수 = 국가 LCI DB 소비 믹스 데이터셋 (2021년 자료, 그대로 사용)
#   그해 계수 = 기준 계수 × (그해 발전소 직접배출 ÷ 기준 연도 국가 전력배출계수)
#   그해 직접배출은 2023년 공식값에 보정한 IPCC 2006 발전 모델 + 제11차 전력수급기본계획 비중
OFF = G["official_by_year_t_per_MWh"]
BASE_YEAR = {"lcidb": DS["elec_market"]["data_year"], "desnz": 2023}


def grid_now(src="lcidb") -> float:
    """기준 전과정 전력 계수 kgCO2e/kWh (국가 LCI DB: 2021년 자료 그대로, 비교용 DESNZ: 2023년 재계산)"""
    return ds("elec_market") if src == "lcidb" else grid_ipcc(2023)


def grid_ratio(year, src="lcidb") -> float:
    """기준 연도 대비 발전소 직접배출 비율 (국가 전력배출계수와 같은 SAR 기준으로 계산한 비율)"""
    return grid_ipcc(year, gwp=GWP_SAR, upstream=False) / OFF[str(BASE_YEAR[src])]


def grid_year(year, src="lcidb") -> float:
    return grid_now(src) * grid_ratio(year, src)


LIFE = F["lifetime"]


def grid_in_year(year, src="lcidb"):
    pts = [(y, grid_year(y, src)) for y in (2023, 2030, 2038)]
    if year <= pts[0][0]:
        return pts[0][1]
    if year >= pts[-1][0]:
        return pts[-1][1]
    for (a, ga), (b, gb) in zip(pts, pts[1:]):
        if a <= year <= b:
            return ga + (gb - ga) * (year - a) / (b - a)


def grid_lifetime_avg(src="lcidb"):
    return float(np.mean([grid_in_year(LIFE["start_year"] + i + 0.5, src) for i in range(LIFE["years"])]))


# ---------------------------------------------------------------------------
# 3. 제조 단계: BMW 공개값 3개로 계수 보정
# ---------------------------------------------------------------------------
A_BODY = V["520i"].bmw_production_t / V["520i"].mass_din_kg
B_PHEV = (V["530e"].bmw_production_t - A_BODY * (V["530e"].mass_din_kg - V["530e"].cell_mass_kg)) / V["530e"].battery_gross_kwh * 1000
B_BEV = (V["i5_40"].bmw_production_t - A_BODY * (V["i5_40"].mass_din_kg - V["i5_40"].cell_mass_kg)) / V["i5_40"].battery_gross_kwh * 1000


@dataclass
class Params:
    lifetime_km: float = LIFE["km"]
    grid: float = field(default_factory=lambda: grid_now("lcidb"))
    gas_comb: float = field(default_factory=gasoline_combustion)
    gas_wtt: float = field(default_factory=gasoline_upstream)
    body_mult: float = 1.0
    b_bev: float = B_BEV
    b_phev: float = B_PHEV
    m_mult: float = 1.0
    elec_mult: float = 1.0
    fuel_mult: float = 1.0
    uf: float = F["phev_uf"]["base"]
    eol: float = F["eol_t"]
    i5_elec: float = 4.6


def production_split(vid, p: Params):
    v = V[vid]
    body = A_BODY * p.body_mult * (v.mass_din_kg - v.cell_mass_kg)
    b = {"BEV": p.b_bev, "PHEV": p.b_phev}.get(v.powertrain, 0.0)
    batt = b * v.battery_gross_kwh / 1000
    if v.group == "performance":
        body *= p.m_mult
        batt *= p.m_mult
    return body, batt


def consumption(vid, p: Params):
    """1 km당 휘발유 L, 전기 kWh"""
    v = V[vid]
    l_km = (1 / v.kr_fuel_km_l) * p.fuel_mult if isnum(v.kr_fuel_km_l) else 0.0
    e_cert = p.i5_elec if vid == "i5_40" else v.kr_elec_km_kwh
    kwh_km = (1 / e_cert) * p.elec_mult if isnum(e_cert) else 0.0
    fs, es = {"ICE": (1, 0), "BEV": (0, 1)}.get(v.powertrain, (1 - p.uf, p.uf))
    return fs * l_km, es * kwh_km


def use_per_km(vid, p: Params):
    L, kWh = consumption(vid, p)
    return {"fuel_supply": L * p.gas_wtt, "elec_supply": kWh * p.grid, "tailpipe": L * p.gas_comb}


def lifecycle(vid, p: Params = None):
    p = p or Params()
    body, batt = production_split(vid, p)
    u = use_per_km(vid, p)
    km = p.lifetime_km
    r = {"body": body, "battery": batt, "fuel_supply": u["fuel_supply"] * km / 1000,
         "elec_supply": u["elec_supply"] * km / 1000, "tailpipe": u["tailpipe"] * km / 1000, "eol": p.eol}
    r["total"] = sum(r.values())
    r["per_km_g"] = r["total"] * 1e6 / km
    return r


def reference_flows(vid, p: Params = None):
    """기준흐름: 기능단위(20만 km)를 채우는 데 필요한 물질·에너지 양"""
    p = p or Params()
    v = V[vid]
    L, kWh = consumption(vid, p)
    km = p.lifetime_km
    return {"vehicle": 1, "mass_kg": int(v.mass_din_kg), "battery_kwh": float(v.battery_gross_kwh),
            "gasoline_L": L * km, "gasoline_kg": L * km * KEI["gasoline_density_kg_per_L"], "electricity_kWh": kWh * km}


def breakeven_km(ev, ref, p: Params = None):
    p = p or Params()
    fe, fr = sum(production_split(ev, p)) + p.eol, sum(production_split(ref, p)) + p.eol
    ue, ur = sum(use_per_km(ev, p).values()), sum(use_per_km(ref, p).values())
    return float("inf") if ur <= ue else max(0.0, (fe - fr) * 1000 / (ur - ue))


def cumulative(vid, p: Params = None, dynamic=False, step=5000, max_km=300_000):
    p = p or Params()
    acc = sum(production_split(vid, p)) + p.eol
    kmy = p.lifetime_km / LIFE["years"]
    xs, ys = [0], [acc]
    for k in range(step, max_km + step, step):
        pp = Params(**{**asdict(p), "grid": grid_in_year(LIFE["start_year"] + (k - step / 2) / kmy)}) if dynamic else p
        acc += sum(use_per_km(vid, pp).values()) * step / 1000
        xs.append(k)
        ys.append(acc)
    return xs, ys


def crossing(xs, a, b):
    for i in range(1, len(xs)):
        d0, d1 = a[i - 1] - b[i - 1], a[i] - b[i]
        if d0 > 0 >= d1:
            return xs[i - 1] + (xs[i] - xs[i - 1]) * d0 / (d0 - d1)
    return None


def params_for_set(src):
    """배경 데이터 세트를 휘발유·전력에 함께 적용"""
    return Params(grid=grid_now(src), gas_wtt=gasoline_upstream(src))


# ---------------------------------------------------------------------------
# 4. Scope 3: 제품 1대 값 → 회사 공시 칸
# ---------------------------------------------------------------------------
SPLIT = F["bmw_footprint_split"]
SALES = F["korea_sales_2025h1"]
GRID_DIRECT_2023 = G["official_2023_t_per_MWh"]   # 공시용 Cat 11 전기: 최신 국가 전력배출계수(2023년) 고정
DIRECT_SHARE = {src: OFF[str(BASE_YEAR[src])] / grid_now(src) for src in ("lcidb", "desnz")}   # LCA 전력 계수 중 발전소 직접배출 몫


def logistics_t(vid):
    s = SPLIT.get(vid)
    return s["logistics"] if s else (1.0 if V[vid].powertrain == "BEV" else 0.4)


def scope_map(vid, p: Params = None, src="lcidb"):
    """BMW 코리아(수입·판매사) 입장의 Scope 3 나누기. 단위 tCO2e/대 (판매 연도에 생애주기 전체 보고)
    Cat 1  : BMW AG에서 사 온 차량의 제조 배출 (원료~공장 출고, BMW 공장 배출 포함)
    Cat 4  : 독일→한국 출고 운송 (BMW 코리아가 운임을 낸다고 가정)
    Cat 11 : 필수 = 사용자 Scope 1(배기) + Scope 2(충전 전기 × 2023년 국가 전력배출계수 0.4173, 계산기 전력 조건과 무관)
             선택 = 연료 생산 + 전기의 연료 채굴·송배전 몫 (LCA 전력 계수의 직접배출 외 부분)
    Cat 12 : 폐차 처리"""
    p = p or Params()
    r = lifecycle(vid, p)
    L, kWh = consumption(vid, p)
    km = p.lifetime_km
    logi = logistics_t(vid)
    cat11_min = (L * p.gas_comb + kWh * GRID_DIRECT_2023) * km / 1000
    cat11_opt = r["fuel_supply"] + r["elec_supply"] * (1 - DIRECT_SHARE[src])
    return {"cat1": r["body"] + r["battery"] - logi, "cat4": logi,
            "cat11_min": cat11_min, "cat11_optional": cat11_opt, "cat12": r["eol"],
            "total": r["total"]}


def korea_inventory(p: Params = None):
    p = p or Params()
    units = {"520i": SALES["520i"], "530e": SALES["530e"], "i5_40": SALES["i5_all"]}
    rows = []
    for vid, n in units.items():
        m = scope_map(vid, p)
        rows.append({"id": vid, "units": n, **{k: v * n for k, v in m.items()}})
    return rows


# ---------------------------------------------------------------------------
# 5. 회피배출 (WBCSD Guidance on Avoided Emissions, 2023)
# ---------------------------------------------------------------------------
def avoided(p: Params = None):
    p = p or Params()
    L = {v: lifecycle(v, p)["total"] for v in V}
    w = {"520i": SALES["520i"], "530e": SALES["530e"]}          # i5 자신은 기준에서 제외
    mkt = sum(L[k] * n for k, n in w.items()) / sum(w.values())
    refs = {
        "R1": {"label": "같은 차급 가솔린 (520i)", "ref": L["520i"], "solution": "i5_40"},
        "R2": {"label": "i5를 뺀 5시리즈 판매 평균 (520i·530e)", "ref": mkt, "solution": "i5_40"},
    }
    out = {}
    for k, r in refs.items():
        per = r["ref"] - L[r["solution"]]
        out[k] = {**r, "solution_total": L[r["solution"]], "per_unit": per,
                  "fleet_h1_2025": per * SALES["i5_all"] if r["solution"] == "i5_40" else None}
    return out


# ---------------------------------------------------------------------------
# 6. 실행
# ---------------------------------------------------------------------------
def main():
    ids = list(V)
    base = Params()

    factors = {
        "gas_comb": base.gas_comb, "gas_comb_co2_only": NCV["gasoline_MJ_per_L"] * 1e-6 * IP["gasoline_road_kg_per_TJ"]["CO2"],
        "gas_wtt_lcidb": gasoline_upstream("lcidb"), "gas_wtt_desnz": gasoline_upstream("desnz"),
        "k_cal": K_CAL, "raw_direct_2023": RAW_DIRECT_2023,
        "direct": {f: direct_kg_per_kWh(f) for f in FUEL},
        "upstream": {f: upstream_kg_per_kWh(f) for f in FUEL},
        "fuel_MJ_per_kWh": {f: fuel_MJ_per_kWh(f) for f in FUEL},
        "share": {str(y): s for y, s in SHARE.items()},
        "grid": {src: {"base": grid_now(src), **{str(y): grid_year(y, src) for y in (2023, 2030, 2038)}} for src in ("lcidb", "desnz")},
        "grid_ratio": {str(y): grid_ratio(y) for y in (2023, 2030, 2038)},
        "official_by_year": {k: v for k, v in OFF.items() if k.isdigit()},
        "direct_share": DIRECT_SHARE, "logistics": {v: logistics_t(v) for v in V},
        "grid_direct": {str(y): grid_ipcc(y, upstream=False) for y in (2023, 2030, 2038)},
        "grid_life_avg": {src: grid_lifetime_avg(src) for src in ("lcidb", "desnz")},
        "grid_direct_official": GRID_DIRECT_2023,
        "a_body": A_BODY, "b_bev": B_BEV, "b_phev": B_PHEV,
        "gasoline_density": KEI["gasoline_density_kg_per_L"],
    }

    rows = [{"id": v, "name": V[v].name, "group": V[v].group, **lifecycle(v, base)} for v in ids]
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "base_results.csv", index=False, encoding="utf-8-sig")

    rf = {v: reference_flows(v, base) for v in ids}
    pd.DataFrame(rf).T.to_csv(OUT / "reference_flows.csv", encoding="utf-8-sig")

    pairs = [("i5_40", "520i"), ("530e", "520i"), ("i5_40", "530e"), ("i5_M60", "M5")]
    be = []
    for a, b in pairs:
        xs, ya = cumulative(a, base, True)
        _, yb = cumulative(b, base, True)
        be.append({"ev": a, "ref": b, "static_km": breakeven_km(a, b, base), "dynamic_km": crossing(xs, ya, yb)})
    be_df = pd.DataFrame(be)
    be_df.to_csv(OUT / "breakeven.csv", index=False, encoding="utf-8-sig")

    set_df = pd.DataFrame([{"set": s, "id": v, "total": lifecycle(v, params_for_set(s))["total"]}
                           for s in ("lcidb", "desnz") for v in ids])

    scen = []
    for label, g in [("base", grid_now()), ("life", grid_lifetime_avg()), ("2030", grid_year(2030)), ("2038", grid_year(2038))]:
        for v in ids:
            scen.append({"scenario": label, "grid": g, "id": v, "total": lifecycle(v, Params(grid=g))["total"]})
    scen_df = pd.DataFrame(scen)
    scen_df.to_csv(OUT / "grid_scenarios.csv", index=False, encoding="utf-8-sig")

    def grid_tie(ev, ref):
        lo, hi = 0.0, 4.0
        for _ in range(60):
            mid = (lo + hi) / 2
            pm = Params(grid=mid)
            (lo, hi) = (mid, hi) if lifecycle(ev, pm)["total"] < lifecycle(ref, pm)["total"] else (lo, mid)
        return (lo + hi) / 2

    tie = {"i5_40_vs_520i": grid_tie("i5_40", "520i"), "i5_M60_vs_M5": grid_tie("i5_M60", "M5")}

    uf_df = pd.DataFrame([{"uf": u, "id": v, "total": lifecycle(v, Params(uf=u))["total"]}
                          for u in np.round(np.linspace(0, 1, 21), 2) for v in ("530e", "M5")])
    uf_df.to_csv(OUT / "phev_charging.csv", index=False, encoding="utf-8-sig")

    # 민감도 (i5 eDrive40과 520i의 차이)
    def saving(p):
        return lifecycle("520i", p)["total"] - lifecycle("i5_40", p)["total"]

    b0 = saving(base)
    sens = []

    def add(label, p_lo, p_hi, lo_txt, hi_txt):
        sens.append({"label": label, "lo_txt": lo_txt, "hi_txt": hi_txt, "saving_lo": saving(p_lo), "saving_hi": saving(p_hi)})

    def P(**kw):
        return Params(**{**asdict(base), **kw})

    add("생애주기 주행거리", P(lifetime_km=120_000), P(lifetime_km=300_000), "12만 km", "30만 km")
    add("실제 연비", P(fuel_mult=0.95), P(fuel_mult=1.2), "공인 0.95배", "공인 1.2배")
    add("충전 전력", P(grid=grid_now()), P(grid=grid_lifetime_avg()), "2021년 고정", "전력계획 반영")
    add("실제 전비", P(elec_mult=1.25), P(elec_mult=0.95), "공인 1.25배", "공인 0.95배")
    add("배터리 제조 배출", P(b_bev=115.0, b_phev=115.0 * B_PHEV / B_BEV), P(b_bev=59.0, b_phev=59.0 * B_PHEV / B_BEV), "115 kg/kWh", "59 kg/kWh")
    add("i5 공인 전비", P(i5_elec=4.1), P(i5_elec=4.8), "4.1 km/kWh", "4.8 km/kWh")
    add("배경 데이터 출처", params_for_set("desnz"), base, "영국 DESNZ+IPCC", "국가 LCI DB")
    add("휘발유 장기 배출 포함", base, P(gas_wtt=gasoline_upstream(longterm=True)), "제외(기본)", "포함")
    add("차체 제조 배출", P(body_mult=1.15), P(body_mult=0.85), "+15%", "−15%")
    add("온실가스 환산 기준", P(gas_comb=gasoline_combustion(GWP_SAR), gas_wtt=gasoline_upstream(gwp=GWP_SAR), grid=ds("elec_market", GWP_SAR)), base, "2차 보고서", "6차 보고서")
    add("휘발유 밀도", P(gas_wtt=gasoline_upstream(density=0.72)), P(gas_wtt=gasoline_upstream(density=0.76)), "0.72 kg/L", "0.76 kg/L")
    sens_df = pd.DataFrame(sens)
    sens_df["swing"] = (sens_df.saving_hi - sens_df.saving_lo).abs()
    sens_df = sens_df.sort_values("swing", ascending=False)
    sens_df.to_csv(OUT / "sensitivity.csv", index=False, encoding="utf-8-sig")

    # 몬테카를로
    rng = np.random.default_rng(20261017)
    N = 20_000
    d = {
        "grid": rng.uniform(grid_year(2023), grid_now(), N),
        "wtt": rng.triangular(gasoline_upstream("desnz"), gasoline_upstream(), gasoline_upstream(longterm=True), N),
        "b_bev": rng.triangular(50, B_BEV, 115, N),
        "body_mult": rng.normal(1, 0.08, N), "m_mult": rng.normal(1, 0.10, N),
        "elec_mult": rng.triangular(0.95, 1.0, 1.25, N), "fuel_mult": rng.triangular(0.95, 1.0, 1.2, N),
        "uf": rng.triangular(0.15, F["phev_uf"]["base"], 0.75, N),
        "km": rng.triangular(120_000, LIFE["km"], 300_000, N),
        "i5": rng.choice([4.1, 4.6, 4.8], N),
    }
    mc = {v: np.empty(N) for v in ids}
    for i in range(N):
        p = Params(lifetime_km=d["km"][i], grid=d["grid"][i], gas_wtt=d["wtt"][i],
                   body_mult=d["body_mult"][i], b_bev=d["b_bev"][i], b_phev=d["b_bev"][i] * B_PHEV / B_BEV,
                   m_mult=d["m_mult"][i], elec_mult=d["elec_mult"][i], fuel_mult=d["fuel_mult"][i],
                   uf=d["uf"][i], i5_elec=d["i5"][i])
        for v in ids:
            mc[v][i] = lifecycle(v, p)["total"]
    mcd = pd.DataFrame(mc)
    mcd.describe(percentiles=[0.05, 0.5, 0.95]).to_csv(OUT / "monte_carlo_summary.csv", encoding="utf-8-sig")
    prob = {"i5_40_lt_520i": float((mcd.i5_40 < mcd["520i"]).mean()), "530e_lt_520i": float((mcd["530e"] < mcd["520i"]).mean()),
            "i5_40_lt_530e": float((mcd.i5_40 < mcd["530e"]).mean()), "i5_M60_lt_M5": float((mcd.i5_M60 < mcd.M5).mean())}
    edges = np.arange(10, 107.5, 2.5)
    hist = {v: np.histogram(mcd[v], bins=edges)[0].tolist() for v in ids}
    pct = {v: {str(q): float(np.percentile(mcd[v], q)) for q in (5, 50, 95)} for v in ids}
    av_mc = (mcd["520i"] - mcd.i5_40)
    av_pct = {str(q): float(np.percentile(av_mc, q)) for q in (5, 50, 95)}

    # 데이터셋끼리 맞는지: 발전원별 데이터셋 × 2023 발전 비중 vs 시장 믹스 데이터셋
    g = g23
    per_src = {
        "coal": (g["coal"] + g["igcc"], ds("elec_coal")), "gas": (g["lng"], ds("elec_ngcc")),
        "oil": (g["oil"], ds("elec_oil")), "nuclear": (g["nuclear"], ds("elec_nuclear")),
        "solar": (g["solar"], ds("elec_pv")), "wind": (g["wind"], ds("elec_wind")),
        "hydro": (g["hydro"] + g["pumped"], ds("elec_hydro")), "fuel_cell": (g["fuel_cell"], ds("elec_fuelcell")),
    }
    covered = sum(a for a, _ in per_src.values())
    bottom_up = sum(a * e for a, e in per_src.values()) / covered

    validation = [
        {"case": "휘발유 연소 CO₂ vs 국가 LCI DB 평가계수(휘발유 육상수송)", "ref": F["upstream_kr_lcidb"]["gasoline_road_combustion_kg_per_L"],
         "model": factors["gas_comb_co2_only"], "unit": "kgCO₂/L"},
        {"case": "휘발유 생산: 국가 LCI DB 데이터셋 vs 영국 DESNZ 2026", "ref": gasoline_upstream("desnz"),
         "model": gasoline_upstream("lcidb"), "unit": "kgCO₂e/L"},
        {"case": "전력: 국가 LCI DB 소비 믹스(2021년 자료) vs IPCC 2006 + DESNZ 재계산(2023년)", "ref": grid_ipcc(2023),
         "model": grid_now("lcidb"), "unit": "kgCO₂e/kWh"},
        {"case": "2023 전력 직접배출 재현 vs 공식 0.4173 (보정 전)", "ref": G["official_2023_t_per_MWh"],
         "model": RAW_DIRECT_2023, "unit": "kgCO₂e/kWh"},
        {"case": "BMW 520i 유럽 사용단계 재현 (WLTP 6.2 L/100km, 20만 km)", "ref": 34.0,
         "model": 6.2 / 100 * 200_000 * (base.gas_comb + base.gas_wtt) / 1000, "unit": "tCO₂e"},
        {"case": "발전원별 데이터셋 합산(2023 비중) vs 생산 믹스 데이터셋", "ref": ds("elec_prodmix"),
         "model": bottom_up, "unit": "kgCO₂e/kWh"},
    ]
    for v in validation:
        v["diff_pct"] = (v["model"] - v["ref"]) / v["ref"] * 100

    # Scope 3, 회피배출
    smap = {v: scope_map(v, base) for v in ids}
    inv = korea_inventory(base)
    inv_life = korea_inventory(Params(grid=grid_lifetime_avg()))
    av = avoided(base)
    av_life = avoided(Params(grid=grid_lifetime_avg()))
    bg = F["bmw_group_2025"]
    bmw_per_vehicle_use = bg["scope3"]["11"] / bg["deliveries_2025"]

    res = {
        "factors": factors, "meta": {**LIFE, "uf": F["phev_uf"]["base"], "eol": F["eol_t"]},
        "vehicles": veh.where(pd.notna(veh), None).to_dict(orient="records"),
        "base": df.round(4).to_dict(orient="records"),
        "reference_flows": rf,
        "breakeven": be_df.to_dict(orient="records"),
        "sets": set_df.round(3).to_dict(orient="records"),
        "grid_scenarios": scen_df.round(4).to_dict(orient="records"),
        "grid_tie": tie,
        "sensitivity": {"base_saving": b0, "rows": sens_df.round(3).to_dict(orient="records")},
        "monte_carlo": {"n": N, "prob": prob, "hist_edges": edges.tolist(), "hist": hist, "pct": pct, "avoided_pct": av_pct},
        "validation": validation,
        "datasets": DS,
        "scope3": {"per_vehicle": smap, "korea_h1_2025": inv, "korea_h1_2025_life_grid": inv_life,
                   "sales": SALES, "bmw_group": bg, "bmw_per_vehicle_use": bmw_per_vehicle_use},
        "avoided": {"base": av, "life_grid": av_life},
        "recycling_example": {"al_alloy": ds("al_alloy"), "al_recycled": ds("al_recycled_ingot"),
                              "avoided_per_kg": ds("al_alloy") - ds("al_recycled_ingot"),
                              "bmw_i5_secondary_al_claim_t": 1.2},
        "grid_bottom_up": {"value": bottom_up, "coverage": covered / g["total"]},
    }
    (OUT / "results.json").write_text(json.dumps(res, ensure_ascii=False, indent=1, default=float), encoding="utf-8")

    pd.set_option("display.width", 220)
    print(json.dumps({k: (round(v, 5) if isinstance(v, float) else v) for k, v in factors.items() if k != "share"},
                     ensure_ascii=False, indent=1, default=lambda x: round(x, 5)))
    print(df[["name", "body", "battery", "fuel_supply", "elec_supply", "tailpipe", "eol", "total", "per_km_g"]].round(2))
    print(pd.DataFrame(rf).T.round(1))
    print(be_df.round(0))
    print(set_df.pivot(index="id", columns="set", values="total").round(2))
    print(scen_df.pivot(index="scenario", columns="id", values="total").round(2))
    print("tie", {k: round(v, 3) for k, v in tie.items()})
    print(sens_df[["label", "lo_txt", "hi_txt", "saving_lo", "saving_hi", "swing"]].round(2), "base", round(b0, 2))
    print("prob", prob, "avoided pct", av_pct)
    print(pd.DataFrame(validation).round(4))
    print(pd.DataFrame(smap).T.round(2))
    print(pd.DataFrame(inv).round(0))
    print(json.dumps(av, ensure_ascii=False, indent=1, default=lambda x: round(x, 2)))
    print("bmw per vehicle use", round(bmw_per_vehicle_use, 2), "bottom-up grid", round(bottom_up, 4), round(covered / g["total"], 3))


if __name__ == "__main__":
    main()
