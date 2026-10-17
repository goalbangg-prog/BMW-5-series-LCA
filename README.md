# 5시리즈 탄소 분석: 제품 LCA에서 Scope 3 공시까지

**웹페이지: https://goalbangg-prog.github.io/BMW-5-series-LCA/**

BMW 5시리즈 다섯 차종이 만들어져 폐차될 때까지 배출하는 온실가스를 **국가 LCI DB 데이터셋**으로 계산하고, 그 결과를 **BMW 코리아의 Scope 3 산정**과 **회피배출 검증**까지 이은 포트폴리오입니다.

- 비교 차종: 일상형 520i(가솔린) · 530e(PHEV) · i5 eDrive40(전기), 고성능 M5(PHEV) · i5 M60(전기)
- 기능단위: 승용차 1대로 200,000 km 주행
- 영향 범주: 기후변화 (GWP100, IPCC 2차 보고서 값: CH₄ 21, N₂O 310)
- 구성: ISO 14044 목표·범위 정의 → 데이터 출처 대장 → 결과 → Scope 3 → 회피배출 → 신뢰도

## 핵심 결과 (기본 조건: 2023년 한국 전력 고정, 20만 km, PHEV 전기 주행 45.5%)

| 차종 | 생애주기 배출 (t) | 1 km당 (g) |
|---|---:|---:|
| 520i | 56.4 | 282 |
| 530e | 54.6 | 273 |
| i5 eDrive40 | 38.5 | 193 |
| M5 | 67.7 | 339 |
| i5 M60 | 43.1 | 216 |

- **제품**: i5 eDrive40은 520i보다 32% 적고, 약 5만 km를 달리면 배터리 제조로 더 낸 몫을 만회합니다. 530e가 520i보다 적게 배출할 확률은 무작위 계산 2만 번 중 63%로, 충전 습관에 따라 갈립니다.
- **공시**: BMW 코리아(수입·판매사) 기준으로 나누면 차량 제조 전체가 Cat 1, 출고 운송이 Cat 4, 사용이 Cat 11, 폐차가 Cat 12입니다. 5시리즈 2025년 상반기 판매분(모델링한 3종 9,456대)의 Cat 11 필수 범위는 약 31.6만 t입니다.
- **회피배출**: 같은 기간 i5 828대를 같은 수의 520i와 비교하면 약 1.48만 t, i5를 뺀 판매 평균(520i·530e)과 비교하면 약 1.45만 t입니다. WBCSD 지침에 따라 Scope 3에서 빼지 않고 따로 보고해야 합니다.
- 웹 계산기에서 조건(주행거리, 전력, 충전 습관 등)을 바꾸면 Scope 3와 회피배출 숫자도 함께 다시 계산됩니다.

## 데이터

| 입력 | 출처 | 비고 |
|---|---|---|
| 휘발유 생산 | KEITI 국가 LCI DB `Gasoline; Production mix, at plant` (c6a62851-83b8-41c5-8e5d-aba03b2b3332) | 대기 배출 원소 흐름을 SAR로 다시 특성화 → 0.7586 kgCO₂e/kg × 0.74 kg/L |
| 충전 전력 (2023년) | KEITI 국가 LCI DB `Electricity, market mix, including T&D losses` (01a4869d-1556-4f7d-ae9a-4eab3f2f27bf) | 2021년 자료 0.5202 × (2023년 국가 전력배출계수 0.4173 ÷ 2021년 0.4509) = 0.481 kgCO₂e/kWh |
| 충전 전력 (2030·2038년) | 2023년 계수 × 제11차 전력수급기본계획 감소 비율 (EPSIS 2023 + 2006 IPCC 고정연소) | 0.317 · 0.184 kgCO₂e/kWh. 모든 연도에 같은 방법 |
| 휘발유 연소 | 2006 IPCC Vol.2 Ch.3 + 에너지열량 환산기준(2022) | 2.142 kgCO₂e/L |
| 제조 | BMW Vehicle Footprint 520i·530e·i5 eDrive40 | M5·i5 M60은 보정 계수로 추정 |
| 연비·전비 | 한국에너지공단 표시연비 (2026.04) | |
| Scope 3 비교 | BMW Group ESG Overview FY2025 | |
| 판매 대수 | BMW 코리아 발표 (2025년 1~6월, 2025.7.7) | 520i 7,116 · 530e 1,512(xDrive 포함) · i5 828(트림 합계) |

데이터셋은 KEITI soda4LCA 노드(http://133.186.241.65)에서 ILCD 형식으로 받았습니다. 쓰지 않은 데이터와 그 이유(평가계수 표의 휘발유 값, 자동차운반선 데이터셋, 발전원별 데이터셋 합산 불일치)는 웹페이지의 "02 데이터"에 정리했습니다.

## 폴더 구성

```
index.html                 # 웹페이지
img/                       # 차량 사진 (위키미디어 공용, CC BY-SA 4.0)
data/vehicles.csv          # 차종별 입력값과 출처
data/factors.json          # 배출계수, 국가 LCI DB 데이터셋 값, Scope 3 입력값과 출처
analysis/lca_model.py      # 계산 모델 (Python: Pandas, NumPy)
outputs/                   # 결과 CSV(기준흐름, 민감도 등)와 results.json
web/index.template.html    # 웹페이지 원본
web/build.py               # results.json을 템플릿에 넣어 index.html 생성
```

## 다시 실행하기

```bash
pip install numpy pandas
python analysis/lca_model.py
python web/build.py
```

웹 계산기는 `lca_model.py`와 같은 식을 JavaScript로 옮긴 것이며, 기본값에서 다섯 차종 결과가 소수점 셋째 자리까지 같은지 확인했습니다.

## 한계

- 기후변화(온실가스)만 계산했습니다. 물 사용, 미세먼지 같은 다른 환경 영향은 넣지 않았습니다.
- 제조 단계는 BMW가 공개한 결과값이라 부품별 투입물을 직접 모은 것은 아닙니다. M5·i5 M60은 추정입니다.
- 국가 LCI DB 데이터셋은 2020~2022년 자료이며 유효기간이 지난 공개 최신본입니다. 전력은 2023년 국가 전력배출계수 비율로 보정했습니다.
- 충전 습관은 국내 통계가 없어 유럽 자료를 썼습니다.
- 공개 비교 LCA는 ISO 14044상 외부 전문가 검토 대상이지만 검토를 받지 않았습니다.
- Scope 3와 회피배출 계산은 방법을 보여주기 위한 예시이며 BMW의 공식 수치가 아닙니다. BMW 코리아의 실제 운임 부담 조건과 트림별 판매 대수는 반영하지 못했습니다.

## 사진

위키미디어 공용 CC BY-SA 4.0: [Damian B Oh](https://commons.wikimedia.org/wiki/File:BMW_G60_520i_M_Sport_Alpine_White_(1).jpg)(520i), [Chanokchon](https://commons.wikimedia.org/wiki/File:2024_BMW_5-Series_530e_M_Sport_Pro.jpg)(530e), [Damian B Oh](https://commons.wikimedia.org/wiki/File:BMW_G60E_i5_eDrive40_M_Sport_PRO_Alpine_White_(6).jpg)(i5 eDrive40), [Alexander Migl](https://commons.wikimedia.org/wiki/File:BMW_M5_(G90)_MYLE_Festival_2025_DSC_9648.jpg)(M5), [Alexander-93](https://commons.wikimedia.org/wiki/File:BMW_i5_M60_IAA_2023_1X7A0397.jpg)(i5 M60). 크기를 줄이고 잘랐으며 M5 사진의 번호판을 흐리게 처리했습니다. 수정본도 같은 CC BY-SA 4.0 조건을 따릅니다.

BMW와 관계없는 개인 분석입니다. BMW, 5시리즈, M5, i5는 BMW AG의 상표입니다.

**만든 사람**: 김수현 · 기후변화·데이터 분석 · 온실가스관리기사 · [포트폴리오](https://goalbangg-prog.github.io/Portfoilo-V4/)
