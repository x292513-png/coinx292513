# 파동 트레이딩 감시

바이낸스 BTCUSDT·ETHUSDT 무기한 선물의 주봉→일봉→4시간봉→15분봉→5분봉 구조를 감시한다. 1분봉은 관심 가격대에 접근한 경우만 분석에 사용한다. 자동 주문 기능은 없다.

## 격리

- 로컬 소스: `/Users/admin/trading-wave-monitor`
- VPS 소스·데이터: `/opt/trading-wave-monitor`
- 수집 서비스: `trading-wave-monitor.service`, 별도 사용자 `tradewave`
- AI 서비스: `trading-wave-ai.service`; 이미 로그인된 `blog`의 Codex 관리 인증을 사용. 인증 파일을 복사하지 않는다.
- 봇 연결: 기존 봇 소스는 그대로 두고 systemd drop-in에서 전용 래퍼로 시작. 새 토픽만 localhost 큐로 전달한다. getUpdates 수신자는 기존 봇 하나다.
- 외부 공개 포트 없음. 상태 API는 127.0.0.1:8791만 사용한다.
- VPS 기본 DNS의 바이낸스 REST 주소 응답이 연결 불가 IP를 반환해, 이 프로그램의 바이낸스 요청에만 HTTPS DNS 조회를 사용한다. 시스템 DNS는 변경하지 않고 원래 도메인의 TLS 인증서 검증을 유지한다.

## 포함 기능

- 실시간 캔들/체결 WebSocket, REST 부트스트랩/주기 보정, 재연결, 체결 누락 표시
- RSI14, ATR 기반 인과적 pivot 확인, 일반 임펄스/ABC/다이아고날/ABCDE 삼각형 후보
- ICT FVG의 정확한 3봉 꼬리 갭/CE 50%, 강한 이탈과 구조 돌파를 동반한 OB 후보/몸통 MT, 접촉·중앙선·완전 메움·무효화 상태
- FVG/OB와 매물대·상위 파동이 겹치는 구간 우선 해석 및 중앙선 접근 감시
- 큰 봉의 이전 해석, 질문/답장 분석 기준을 SQLite에 유지
- 7일 5분봉 근사 매물대, 최근 4시간 큰 스윙 근사 매물대, 수집한 실제 체결 분포(별도)
- 15분 종가 구조 점검, 관심 가격대·무효화·확인가격 감시; 의미 있는 변화에 AI 호출
- 6개 시간봉 이미지와 실제 숫자를 AI에 전달; 라벨 시각/가격 검증 후 차트 표시
- 한국어 결론·확신도·대안·가격대·무효화·변경 이유·RSI·매물대·차트 링크/이미지
- 동일 분석 반복 알림 억제, 수집은 AI 실패/한도 이후에도 지속
- 텔레그램 답장 대화, 상태/일시중지/재개/검증 명령
- 1h/4h/24h 가격경로 평가, 일일 보고서, 시작 7일 후 검증 보고서 자동 생성/전달

## 운영 한도

`config/settings.json`에 설정. 최초 자동 AI 호출 한도는 하루 48회, 사용자 질문 12회(KST), 동시 실행 1개다. 숫자는 통계적 적중률이 아닌 해석 확신도다. 조용한 시장은 2시간마다 AI 재평가하며 구조 계산은 15초마다, 확정 봉은 종가 기준이다. 이미 분석 대기 중이면 같은 종목의 자동 작업을 합친다.

AI는 외부 Codex 모델에서 실행되며 현재 구독의 한도를 소비할 수 있다. 무제한 무료라고 가정하지 않는다. 별도 API 비용을 쓰는 경로는 현재 활성화하지 않는다.

## 명령

```sh
systemctl status trading-wave-monitor trading-wave-ai
curl -s http://127.0.0.1:8791/health
journalctl -u trading-wave-monitor -u trading-wave-ai --since '1 hour ago'
cd /opt/trading-wave-monitor
.venv/bin/python -m unittest discover -s tests -v
```

텔레그램 전용 토픽에서 `BTC 분석`, `ETH 분석`, 기존 알림에 질문 답장. `/status`, `/report`, `/pause`, `/resume` 지원.

## 과거 사례 학습 · 2026-09-11 추가

`trading-wave-learning.service`가 4시간마다 바이낸스 공개 API의 최초 제공 봉부터 최신 확정 봉까지 증분 수집한다. BTC·ETH × 현물·USDT 무기한 선물 × 월봉·주봉·일봉·4시간봉을 `data/history.sqlite3`에 분리 보관한다. 기존 45일 분봉 보존과 별개로 이 과거 원장은 삭제하지 않는다. 최초 검증 수집량은 83,647봉이다. 바이낸스 BTC 현물은 2017년, 선물은 2019년부터이며 비트코인 탄생 이후 전 거래소 역사를 의미하지 않는다. 월봉의 첫 봉은 상장월 일부 기간일 수 있다.

이는 모델 가중치 재훈련이 아니라, 지속 갱신하는 사례 기록을 각 AI 분석에 제공하는 방식이다. 별도 학습용 AI 호출은 없다. 원시 가격 검증, 출처·첫날·마지막 확정시점·시간 공백, 개별 후보의 관측 완료 시각을 기록한다. 오래된 현물의 시간 공백은 표시하고 해당 구간을 가로지르는 유사 창은 제외한다.

- 유사사례: 최근 최대 32봉의 종가 경로를 로그수익률 변동성으로 정규화해 비교한다. 미래 결과는 비교 점수에 쓰지 않고, 현재 분석 창과 겹치거나 결과가 아직 나오지 않은 사례는 제외한다. 사례끼리도 관찰 창과 사후 창이 겹치지 않게 최대 12개를 고른다. 이후 월봉 3봉·주봉 4봉·일봉 7봉·4시간봉 12봉의 움직임을 확인한다. 최근 사례의 가중치는 `0.25 + 0.75 × exp(-경과일/365)`이다. 검증된 예측 확률이나 수익률 모델로 해석하지 않는다.
- FVG: 강한 이탈을 동반한 3봉 갭을 형성 후 24봉 관찰한다. CE 접촉, CE 전 1 ATR 추세 연장, CE 후 0.5 ATR 종가 반응, 반대 경계 종가 무효화를 구분한다. 같은 봉에서 접촉과 무효화가 겹치면 별도 분류한다. 같은 방향의 관찰 창을 겹치지 않게 한다.
- 삼각형: 확정된 교대 고저점 4개가 수렴할 때 A-C 선을 투영한다. D 확인 이후 24봉 이내에 선의 0.75 ATR 안에서 극단값 대비 0.5 ATR 종가 반응을 관측한다. 선까지 남은 거리가 0.15 ATR보다 크면 선 전 반전, ±0.15 ATR이면 선 부근, 그 밖으로 넘었다면 선 초과 후 반전으로 분류한다. E파의 정답이나 매수자의 의도를 확정하는 규칙이 아니다.
- 최근 90일·365일·이전 기간·전체를 나눠 비교하며, 표본 20건 미만은 작다고 표시한다. 현물·선물 표본은 합산하지 않는다. 실제 발표한 분석의 1/4/24시간 사후 결과도 다음 분석에 전달한다.

`/learn`은 수집 범위와 최근 패턴 비교를 AI 호출 없이 보여준다. 상태와 통계는 `data/learning-summary.json`, 사례는 별도 DB의 `samples` 테이블에 남는다. 갱신이 10시간 이상 지연되면 분석 입력에 오래된 자료로 표시한다. 서비스는 CPU 최대 20%, 메모리 최대 384MB로 제한한다.

## 텔레그램 표시 · 2026-09-11 추가

핵심 판단·관심 가격·확인/무효화를 먼저 보여주고 시간봉 근거, ICT/매물대/RSI, 대안, 과거 사례는 Telegram HTML의 `<blockquote expandable>`로 접는다. 굵은 제목과 이모지로 구분하고, 모든 모델 문장을 HTML 이스케이프한다. 긴 메시지는 완결된 블록 사이에서만 나눠 태그가 깨지지 않게 한다. 첫 메시지만 일반 알림이며 이어지는 상세 메시지·차트는 소리 알림을 중복시키지 않는다. 기존 답장 연결은 유지한다.

자동 분석 빈도와 하루 상한은 그대로다. 기존 ChatGPT 관리 로그인을 사용하고 API 키 환경변수는 하위 프로세스에 전달하지 않는다. 크레딧 구매·자동 충전·다른 유료 API로의 전환 코드는 없다. AI 해석은 구독 한도를 사용한다. 계정에 별도 크레딧이 있다면 제공자의 한도 초과 정책에 따라 쓰일 수 있으므로 영구적인 무과금을 보증하는 설정과는 다르다.

추가 근거: [Telegram HTML 형식](https://core.telegram.org/bots/api#html-style), [바이낸스 선물 시세 API](https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data), [바이낸스 현물 시세 API](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market), [OpenAI 공식 사용량·크레딧 안내](https://learn.chatgpt.com/docs/pricing).

## 정확성 경계와 검증

자동 ZigZag는 Elliott 정답 탐지기가 아니라 후보 생성기다. 후행 pivot은 confirmation timestamp를 기록하고 미확정 끝점은 별도 표시한다. 차트는 확정 캔들, 현재가격은 시간 표시된 별도 실시간 값이다. 3파 길이 규칙은 5파가 확보된 경우만 검사한다. 삼각형과 리딩/엔딩은 구분한다.

매물대 근사는 캔들의 가격범위에 거래량을 균등 분배하며 TradingView 계산과 같다고 주장하지 않는다. 실제 체결 프로필도 수집 시작 이후 관측분이며 재연결 누락/분해능을 표시한다. 실제 프로필이 충분히 쌓이기 전부터 과거 분포인 것처럼 표시하지 않는다.

평가는 실제 거래·손익이 아닌 당시 발표된 시나리오의 이후 가격 경로다. 한 1분봉에서 목표·무효화가 모두 닿으면 순서 불명으로 기록한다. 일주일 결과는 운영 검증이며 수익성 입증이 아니다.

## 롤백

새 서비스를 중지하고 `/etc/systemd/system/telegram-opsbot.service.d/90-trading-wave.conf`만 제거한 후 daemon-reload 및 기존 봇 재시작. 기존 봇 원본과 다른 서비스 설정은 수정하지 않는다. 분석 기록/설정/인증은 삭제하지 않는다.

## 공식 근거

- https://developers.openai.com/codex/noninteractive
- https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market
- https://www.tradingview.com/support/solutions/43000502040-volume-profile-indicators-basic-concepts/
- ICT FVG 원본: https://www.youtube.com/watch?v=Bkt8B3kLATQ (2022 Mentorship Episode 6)
- ICT OB 원본: https://www.youtube.com/watch?v=PIYh0CxoY9c (Core Content Month 04 Orderblocks, 약 01:00~05:30 정의/검증/이탈 설명)

ICT 자동 후보 조건: 3봉 갭 크기 >= ATR의 0.1, 가운데 봉 몸통 >= ATR의 0.8이면 강한 이탈로 표시. OB는 이탈 직전 8봉 안의 마지막 반대색 봉, FVG 발생, 직전 확정 swing 또는 근접 5봉 범위의 종가 돌파를 함께 요구한다. 이는 반복 검증 가능한 운영 정의이며 모든 ICT 재량적 해석의 유일한 정의라고 주장하지 않는다. FVG는 꼬리 경계의 중앙(CE), OB는 몸통 중앙(MT)과 전체 꼬리 범위를 각각 보존한다. 세 번째 봉이 마감된 뒤에만 구간을 생성하고 그 뒤 봉부터 재방문을 센다.
