# Slack 상담 연결

전용 앱: GPT Trading (`A0CHUFF6AG1`), 워크스페이스 `T0B8S5BKRJR`, 채널 `C0CHL9US751`.
앱 설정은 `config/slack-app-manifest.json`, 서비스는 `systemd/trading-wave-slack.service`.

## 동작

- 사용자님의 일반 채널 메시지를 받아 채널 본문으로 답한다. 멘션·스레드 불필요.
- 최근 2시간, 최대 24개 채널 메시지로 후속 질문의 종목·맥락을 이어간다.
- 휴대폰에서 관측된 GPT 멘션 별칭도 인식한다. 그록만 명시적으로 부른 메시지는 건너뛴다.
- Grok 의견은 참고 맥락. 봇 발언 자체로 GPT 호출하지 않음.
- 최신 가격·캔들, 독서 기록, 가상계좌를 기존 모듈에서 읽는다.
- 이 Codex 대화 세션이 그대로 이동하는 것은 아니다. 상담 기준은 `knowledge/slack-consultation.md`로 명시한다.
- 기존 매매 주문·텔레그램 경로를 호출하지 않는다. Slack 상담에서 주문 변경 불가.
- AI는 허용된 사용자의 질문으로만 호출. 유휴 Socket 연결/재접속에 AI 호출 없음.
- `data/slack.sqlite3`에 이벤트 중복 제거, 스레드 맥락, 처리/전송 상태를 저장한다.
- 이미지 요청 시 현재 측정 차트를 첨부한다. 새 상담의 파동 라벨을 그린 차트로 과장하지 않는다.

## 비공개 설정

`config/slack-runtime.json` (Git 제외, `blog:tradewave`, 0600):

```json
{"team_id":"T0B8S5BKRJR","channel_id":"C0CHL9US751","allowed_user_ids":["U0B8E2XCPLP"],"channel_chat":true,"mention_aliases":["B0CHSDCCQLA"],"bot_token":"REPLACE_PRIVATELY","app_token":"REPLACE_PRIVATELY"}
```

앱 토큰 범위는 `connections:write`. 봇 범위는 manifest 참조. 관리자/개인 DM/개인 사용자 토큰 권한 없음.
공개 채널 기록은 봇 참여 채널에 한정되며, 코드에서도 위 채널/사용자를 추가 제한한다.

## 운영

```sh
systemctl status trading-wave-slack
journalctl -u trading-wave-slack -n 30 --no-pager
systemctl restart trading-wave-slack
```

정상 로그는 `ready channel=... bot=...`, `socket_connected`. 로그에 토큰과 원문 API 응답을 기록하지 않는다.
전송 실패는 저장된 답변을 재전송하며 AI 재호출하지 않는다. 생성 중 재시작된 요청은 재생성될 수 있다.
Slack 외부 전송 후 로컬 저장 전에 종료되면 드문 중복 가능성이 있으며 동일 `client_msg_id`를 재사용한다.

검증: `python -m unittest discover -s tests -p test_slack_bot.py -v`.
