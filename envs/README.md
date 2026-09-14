# 환경 변수 가이드

> 2026-09-14 갱신. 환경 전환 스크립트(`./env local` 등)와 환경별 config 묶음은 **폐지**됐다.
> 환경 구분은 `.env` 안의 **`ENV` 한 줄**로 한다.

## 파일 구조

```
.env.example              # 로컬 템플릿 (git 추적) — 이것만 보면 필요한 키를 알 수 있다
.env                      # 로컬 실값 (git 미추적)
envs/example.gcp-login.env  # 프로덕션(GCP) 키 목록 참고용 (git 추적, 실값 아님)
```

프로덕션 실값은 **저장소에 두지 않는다**. VM 위의 `.env`(서버측)와 GitHub Actions secrets 가 공급원이다.

---

## 로컬 개발 시작

```bash
# 1) 환경변수 준비 (최초 1회)
cp .env.example .env
#    이후 .env 안의 SECRET_KEY / DB_PASSWORD / KAKAO_* 를 실제 값으로 채운다

# 2) 백엔드 스택 기동 (postgres / redis / fastapi / ai-worker)
docker compose up -d
docker compose ps
curl -i http://localhost:8000/api/v1/health   # 200 이면 정상

# 3) 프론트엔드
cd medication-frontend && npm run dev          # http://localhost:3000
```

로컬에는 **nginx 가 없다**. 프론트(:3000)가 백엔드(:8000)를 **직접(cross-origin)** 호출하며,
백엔드가 `http://localhost:3000` 을 CORS(allow_credentials)로 허용한다. 이는 프로덕션의
"독립 API" 토폴로지와 같은 구조다(dev/prod 패리티).

---

## 환경 구분 — `ENV` 한 줄

| ENV | 용도 | 카카오 로그인 |
|---|---|---|
| `local` | 로컬 Docker | **mock IdP**(테스트 대역). mock 라우터는 이때만 등록됨 |
| `dev` | 로컬 Docker | 실제 카카오 서버(실테스트) |
| `prod` | 배포 환경 | 실제 카카오 서버 |

`.env` 의 `ENV` 와 `NEXT_PUBLIC_ENV` 를 같은 값으로 맞춘다.

> ⚠️ **`ENV` 는 필수값이다(기본값 없음).** 미설정 시 앱이 기동 단계에서 실패한다.
> 과거 기본값은 `local` 이었는데, 설정이 유실되면 프로덕션이 조용히 local 로 떠서
> mock IdP 가 등록되고 prod 필수값 검증까지 건너뛰는 **fail-open** 구조였다.

`ENV` 에 따라 백엔드(`app/core/config.py`)가 아래를 자동 적용한다:

- `local`/`dev`: `API_BASE_URL=http://localhost:8000`, `FRONTEND_URL=http://localhost:3000`,
  `KAKAO_REDIRECT_URI=http://localhost:3000/auth/kakao/callback`, `COOKIE_DOMAIN=localhost`
- `prod`: **하드코딩 폴백 없음**(플랫폼 중립·12-factor). `API_BASE_URL`·`FRONTEND_URL` 을
  `.env` 로 반드시 주입해야 하며 누락 시 기동 단계에서 차단된다.

> ⚠️ **개발자 로그인 백도어는 제거됐다**(보안 하드닝). `ENV=local` 이어도 로그인 화면에
> "개발자로 로그인" 버튼은 없다. 인증이 필요한 E2E 는 별도 전략이 필요하다.

### `NEXT_PUBLIC_API_BASE_URL` 주의
로컬에서는 **설정하지 말 것.** 미설정 시 프론트가 `medication-frontend/src/config/env.js` 의
환경별 기본값(local/dev = `http://localhost:8000`)을 쓴다. 여기에 값을 적으면 그 값이 기본값을
덮어쓰므로 토폴로지가 바뀌었을 때 그 줄만 낡아 조용히 깨진다(실제로 `http://localhost`(:80)를
가리켜 로컬 API 호출이 전부 실패한 이력이 있다). 프로덕션에서는 CI/배포가 주입한다.

---

## 프로덕션

- 구성: **Cloudflare Pages(프론트)** + **GCP VM 위 Docker(백엔드)** + **Neon(PostgreSQL)** +
  **Cloudflare Tunnel**. compose 파일은 `docker-compose.gcp-login.yml`.
- 배포: `main` push → GitHub Actions(`.github/workflows/deploy.yml`) → 이미지 빌드(ghcr) →
  WIF(keyless)+IAP SSH 로 VM 에서 pull & up → health check. **VM 에서 빌드하지 않는다.**
- 환경변수: VM 위의 `.env`(서버측에서 관리). 필요한 키 목록은 `envs/example.gcp-login.env` 참고.
- 상세(아키텍처·배포 절차·보안 태세)는 `docs-private/` 의 배포 문서를 따른다.
