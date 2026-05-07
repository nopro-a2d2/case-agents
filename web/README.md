# case-agent web frontend

TUI(`tui-ts/`)와 같은 시각/로직을 가진 브라우저 UI. 백엔드는 `case_agent`의 `serve`
서브커맨드(WebSocket 어댑터)를 그대로 사용하므로 별도 서비스 코드는 없다.

---

## 1. 개발 모드 (vite dev + 별도 백엔드)

터미널 1 — 백엔드:
```
uv sync --extra web
python -m case_agent serve --case <id> --root <path> --port 8765 --static-dir ""
```
(`--static-dir ""`로 정적 서빙을 끄면 vite가 정적 자산을 담당한다.)

터미널 2 — 프런트:
```
cd web
npm install
npm run dev   # http://localhost:5173
```

브라우저:
```
http://localhost:5173/?case=<id>&root=<path>
```
vite가 `/ws`를 `ws://127.0.0.1:8765`로 프록시한다.

---

## 2. 서버 배포 (단일 포트, IP/LAN 접근)

빌드는 한 번만:
```
cd web && npm install && npm run build   # web/dist/ 생성
```

서버에서 단일 명령으로 기동:
```
uv sync --extra web
python -m case_agent serve \
    --case <id> --root <path> \
    --host 0.0.0.0 --port 8765
# --static-dir 생략 시 web/dist 자동 감지
```

같은 네트워크의 클라이언트에서:
```
http://<server-ip>:8765/?case=<id>&root=<path>
```

브리지 코드(`src/bridge.ts`)가 `window.location.origin`을 그대로 따라가므로
어떤 호스트로 접근해도 WS 업그레이드 경로(`/ws`)가 자동으로 일치한다. HTTPS
뒤에 두면 자동으로 `wss://`로 업그레이드된다.

### 보안 메모

- `--host 0.0.0.0`은 LAN 노출이다. **공용 인터넷에 직접 띄우지 말 것.**
  외부 노출이 필요하면 nginx/caddy 등 리버스 프록시 + 인증을 앞단에 두자.
- 현재 인증/세션 관리 없음 → 브라우저 한 탭당 독립적인 case+history.
- HTTPS/WSS는 리버스 프록시에서 종단 처리(uvicorn 자체 TLS는 v1 미지원).

---

## 3. Protocol

`tui-ts`/`headless`와 **동일한 NDJSON 이벤트 스키마**를 WebSocket 텍스트
프레임으로 주고받는다 (`case_agent/loop/headless.py:_serialize`). 클라이언트는
추가로 `{"type":"abort"}`를 보낼 수 있다.

## 4. Keys

- `Enter` 전송 (`Shift+Enter` 줄바꿈)
- `Shift+Tab` plan mode 토글
- `Esc` (대기 중) abort
