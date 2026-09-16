# 문헌 조사 — 근거와 적용 경계

조사일 2026-09-16. 저자·학술지·NBER·SSRN·운용사 원문을 우선했다. SSRN은 게재 자체가 peer review를 의미하지 않는다.
수익 수치의 전이보다 반복되는 설계 원칙을 추출한다. 아래 요약은 특정 BTC 수익률을 예측하지 않는다.

| 연구 / 저자 / 연도 / 출판 | 데이터 기간 | 대상 | 신호·방법 | 주요 결과 | 한계 | BTC 적용 |
|---|---|---|---|---|---|---|
| [Time Series Momentum](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum), Moskowitz, Ooi, Pedersen, 2012, JFE | [원논문 요인 데이터](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Original-Paper-Data) 1985.01–2009.12 | 전통자산 선물·선도 58개, 주식·채권·통화·원자재 | 12개월 초과수익 부호, 월간 보유, 변동성 정규화, long/short | 여러 자산과 하위표본에서 시계열 모멘텀, 장기에는 일부 반전 | 분산·숏·선물과 단일 BTC 현물은 다름. BTC MA120 근거가 아님 | 추세와 노출 규모를 구분; 단기 잡음에 비해 느린 신호를 우선 |
| [A Century of Evidence on Trend-Following Investing](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf), Hurst, Ooi, Pedersen, 2017, JPM | 1880.01–2016.12, 시장별 시작 상이 | 전통자산 67시장 | 1/3/12개월 신호 결합, 월간 재조정, 변동성 배분 | 긴 역사와 다수 국면에서 지속성, 분산 포트폴리오의 위기 대응 | 과거 자료 복원·비용 추정, 단일자산 방어력을 보장하지 않음 | 전체 한 구간보다 여러 사이클, 실행 지연·비용에 대한 검증 |
| [A Quantitative Approach to Tactical Asset Allocation](https://mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf), Mebane Faber, 2007 JWM / 2013 업데이트 | 2013판: 미국 주식 장기 표본 1900–2012, 5자산 1973–2012 | 미국·해외주식, 국채, 원자재, 부동산 | 월말 종가 vs 10개월 SMA, 하회 시 현금성 자산 | 주 목적은 하방·변동성 완화, 업데이트에서 실시간 이후도 검토 | 횡보 휩쏘, 현금 이자와 월말 drawdown 측정, BTC 미포함 | 10개의 월말 관측치 그대로 독립 후보; BTC 200일로 오인하지 않음 |
| [Absolute Momentum: a Simple Rule-Based Strategy and Universal Trend-Following Overlay](https://naaim.org/wp-content/uploads/2013/10/00D_Absolute-Momentum_gary_antonacci.pdf), Gary Antonacci, 2013, working paper | 원자료 1973부터, 비교 1974.07–2012.12; HY는 후발 | 전통 주식·채권·REIT·금·원자재 | 12개월 T-bill 초과수익 양수면 보유, 아니면 T-bill, 월 판단, 20bp 비용 | 여러 자산에서 하방 위험 감소 | lookback 탐색 포함, 독립 표본 한계, BTC와 현금 이자가 다름 | long/cash의 단순함 지지. 별도의 12개월 후보까지 늘리지 않음 |
| [The Real-Life Performance of Market Timing with Moving Average and Time-Series Momentum Rules](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2242795), Valeriy Zakamulin, 2014, Journal of Asset Management | 확보한 저자 SSRN 초록은 세부 시작/종료 미기재 — 본문 기간 검증 보류 | 전통 주식 타이밍 | MA/시계열 모멘텀의 OOS와 현실적 비용 | 기존 성과가 데이터마이닝·시장 마찰 무시로 과장됨 | 이번 접근 가능 초록으로는 표별 수치/기간 검증 불가 | 최고값 선정 금지, 비용 포함, 미래 시점 분리의 직접 근거 |
| [Market Timing with Moving Averages: Anatomy and Performance of Trading Rules](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2585056), Zakamulin, 2015/2016 working paper; [2017 저서](https://link.springer.com/book/10.1007/978-3-319-60970-6) | 이론적 신호 구조 연구; 저서의 표별 실증 기간은 이번 조사에서 확인하지 않음 | 전통자산 / 추세 필터 이론 | MA·모멘텀·평균 기울기의 가중 구조 비교 | 이름이 다른 신호도 유사 정보를 가중·지연해 사용 | 기울기 추가가 독립 예측력이라는 뜻은 아님 | MA120+기울기+가격 확인의 중복 조건 누적을 피함 |
| [Simple Technical Trading Rules and the Stochastic Properties of Stock Returns](https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.1992.tb04681.x), Brock, Lakonishok, LeBaron, 1992, JoF | 1897–1986 | DJIA | 이동평균·trading-range breakout; band 방식 포함 | 매수/매도 조건부 수익 차이 | 오래된 단일 시장, 실제 비용·후속 선택 문제. 1%가 BTC의 정답은 아님 | buffer의 거래 억제 논리는 타당하나 기존 1%만 비교; 새 threshold 탐색 안 함 |
| [Volatility-Managed Portfolios](https://www.nber.org/papers/w22208), Moreira, Muir, 2016 NBER / 2017 JoF | 미국 시장 장기 표본 1926–2015; 요인별 상이 | 전통 주식 요인·통화 carry | 직전 실현분산 역수에 따른 월별 위험 조절 | 고변동 때 비중 축소가 여러 요인의 위험조정 성과 개선 | inverse variance와 본 프로젝트 inverse volatility는 다름; 레버리지·정규화 차이 | 변동성 군집을 통한 위험 예산 근거, BTC 수익 개선 근거로 단정 금지 |
| [The Impact of Volatility Targeting](https://www.man.com/insights/the-impact-of-volatility-targeting), Harvey, Hoyle, Korgaonkar, Rattray, Sargaison, Van Hemert, 2018, JPM / Man | 미국 주식 1926부터, 60여 자산별 상이; 공개 요약에 전체 종료일 미기재 | 전통 주식·신용·채권·FX·원자재 | 변동성에 반비례한 노출 | 주식/신용 Sharpe 개선, 다른 자산은 미미; tail 완화 | 자산별 효과 다름, 레버리지 효과가 BTC에 동일하지 않음 | 무레버리지 주간 vol 후보 하나만; 40% 목표는 사전 예산 |
| [On the Performance of Volatility-Managed Portfolios](https://www.lehigh.edu/~xuy219/research/COWY.pdf), Cederburg, O’Doherty, Wang, Yan, 2020, JFE | 요인별 기간 상이; 이번 확보 초록으로 세부 표본기간 검증 보류 | 전통 주식 전략 103개 | 변동성 관리와 실시간 구현/OOS 비교 | 직접 비교에서 체계적 우위 없음, 사후 회귀 조합의 이득이 OOS로 전이 안 됨 | 모든 위험 관리가 무가치하다는 뜻은 아님 | vol 후보를 자동 채택하지 않고 단순 저노출과 구분 |
| [Risks and Returns of Cryptocurrency](https://www.nber.org/papers/w24877), Yukun Liu, Aleh Tsyvinski, 2018 NBER / 2021 RFS | 2018 WP의 BTC 2011.01–2018.05, 코인별 시작 상이; 후속 저널판은 별도 판본 | **직접 암호자산** BTC·XRP·ETH | 시계열 수익 모멘텀·투자자 관심 예측 회귀 | 암호자산 고유 모멘텀과 관심의 예측력 보고 | 120일 MA 또는 현재 분할비중을 테스트한 연구 아님; 초기 시장 중심 | 추세 가설을 직접 뒷받침하되 특정 일수/필터 정당화에는 사용 불가 |
| [A Decade of Evidence of Trend Following Investing in Cryptocurrencies](https://arxiv.org/html/2009.12155v1), Rozario, Holt, West, Ng, 2020, arXiv preprint | 2011.09.13–2019.12.12 | **직접 BTC** Bitstamp, S&P 비교 | 시간봉 SMA/EMA/DEMA; 연별 lookback 최적화 walk-forward | 높은 장기 수익을 보고하나 일부 연도 검증은 부진/불안정 | 비용·spread·slippage 무시, 초기 결측 5,835/72,299 관측을 ffill, 대규모 최적화, peer review 미확인 | 주의 사례로 채택. 논문의 최고값·headline CAGR은 전략 설계에 사용하지 않음 |

## 반복되는 것과 반복 입증되지 않은 것

- **상대적으로 강한 전통자산 근거:** 중장기 방향 지속, 월간 등 느린 관측, 위험 노출 조절, 다양한 시장·긴 기간·비용 검증. 다자산 long/short 성과를 BTC long/cash 성과로 전이할 수 없다.
- **설계 논리는 있지만 특정 값의 근거가 약함:** N일 확인은 짧은 되돌림을 무시하고 진입을 지연한다. buffer는 작은 교차 왕복을 줄이고 반대 추세 인식을 늦춘다. 주간은 일정·거래부담 감소의 응용이며 일요일의 우위는 입증되지 않았다.
- **이번에 제외:** 장기선 기울기와 가격 AND 필터는 상관된 추세 정보의 중복 사용, ATR 배수·ADX threshold는 추가 자유도. 독립적인 증분 효용 근거를 확보하지 못했다.
- **부분진입/부분청산:** 전환 시점 집중을 완화할 수 있지만 50/75/100 및 50/25/0 수치는 사용자 정책이다. 경제학적 최적해로 취급하지 않는다. 비대칭은 급락 대응과 상승 참여의 trade-off를 만들며 원안/개선 비교로 충분하다.
- **행동적 해석:** 정보에 대한 과소반응, anchoring, 군집, 손실 종목 보유 성향은 추세 지속의 설명 후보다. 이 문헌만으로 BTC의 인과기제가 식별된 것은 아니다.
- **시장 미시구조:** 잦은 체결에는 bid–ask·수수료·불리한 체결 위험이 누적된다. 완충/저빈도는 이를 낮출 수 있으나 갑작스러운 급락과 V자 회복에서 손실도 늦춘다.

검증 미완료된 표본 기간은 추정으로 채우지 않았다. 이 행들은 정량 결론의 근거로 사용하지 않으며, 접근 가능한 원문에서 확인한 설계/한계만 반영한다.
