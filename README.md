# Stock Alarm

Supabase를 백엔드로 활용해 미국 주식의 비정상 거래량 급증을 자동으로 감지하고 웹 사이트로 공개하는 프로젝트입니다.

## 앞으로 진행할 과제
- Supabase에 `supabase_schema.sql`을 적용하고 서비스/anon 키를 환경 변수 및 GitHub Secret에 등록합니다.
- `python -m pipeline.run --dry-run`으로 파이프라인을 시범 실행하여 데이터 형식과 API 응답을 검증합니다.
- GitHub Actions 스케줄이 정상 동작하는지 모니터링하고, 필요 시 `CHUNK_SIZE`나 실행 빈도를 조정합니다.
- Docker 이미지를 Azure App Service에 배포하고 환경 변수를 설정해 실제 트래픽을 점검합니다.
- 장기적으로는 알림 채널(이메일/SMS) 연동, 히스토리 뷰, 인증 등 추가 기능을 계획합니다.

## 프로젝트 구조

```
stock_alarm/
  pipeline/               # GitHub Actions 및 CLI 파이프라인
  web/                    # FastAPI 웹 애플리케이션과 정적 자산
  .github/workflows/      # 정기 실행 워크플로
  Dockerfile              # Azure 배포용 컨테이너 이미지 정의
  requirements_pipeline.txt
  web/requirements.txt
  supabase_schema.sql     # Supabase 초기 스키마 스크립트
  .env.example            # 로컬 개발용 환경 변수 템플릿
  us_tickers.csv          # 대상 미국 주식 티커 목록
```

## 데이터 파이프라인

1. `pipeline/run.py`는 `us_tickers.csv`에서 티커를 읽고, 200개 단위 배치로 순차 처리합니다. 각 배치마다 `yfinance.Ticker().history(period="3d")`를 우선 호출하고, 부족하면 `start/end` 범위, 마지막으로 `period="5d"`를 시도합니다. 배치 간에는 기본 10초씩 대기합니다.
2. 스크립트는 아래 지표를 계산합니다.
   - `volume_change_pct`: 직전 거래일 대비 거래량 증감 비율(%)
   - `volume_ratio`: 최신 거래량 ÷ 직전 거래량
   - `is_spike`: `volume_ratio >= 2`일 때 `True`로 표기하여 2배 이상 급증한 종목 강조
   - `fetched_at_*`: 수집 시점을 UTC와 KST(UTC+09:00)로 모두 기록하여 운영자의 표준시를 반영
   - 거래량 데이터가 두 날짜 이상 존재하고 두 값 모두 0보다 큰 경우에만 백분율을 산출한 뒤 업로드합니다.
3. 결과는 Supabase REST API로 업로드되며, 실행마다 부여되는 `batch_id`로 히스토리를 구분합니다.

### 로컬 실행 방법

```bash
python -m pip install -r requirements_pipeline.txt
cp .env.example .env  # Supabase 관련 값을 입력
python -m pipeline.run --log-level DEBUG  # 빠른 검증용 --limit 20 옵션 권장
```

`--dry-run` 옵션을 사용하면 Supabase에 쓰기 없이 첫 5건을 미리 확인할 수 있습니다.

### GitHub Actions 자동화

`.github/workflows/fetch_volumes.yml`은 매일 00:00/06:00/12:00/18:00(UTC)에 파이프라인을 실행합니다. 실행 전에 아래 Secret을 저장하세요.

- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`

필요하다면 워크플로 `env` 블록에서 `CHUNK_SIZE`, `BATCH_PAUSE_SECONDS`, `YF_PERIOD` 등을 덮어쓸 수 있습니다.

## Supabase 설정

1. 프로젝트 DB를 만든 뒤 스키마 파일을 실행합니다.
   ```sql
   \i supabase_schema.sql
   ```
2. 테이블 구성 요소
   - `id BIGSERIAL PRIMARY KEY`: 100행 단위 페이지네이션 및 정렬용 기본 키
   - `created_at timestamptz DEFAULT timezone('utc', now())`: 업로드 시점을 기록
   - `batch_id`, `volume_change_pct`, `ticker` 컬럼에 인덱스를 생성해 조회 속도를 확보
3. 행 수준 보안을 활성화하고 `SELECT` 전용 정책을 추가했습니다. 서비스 키는 삽입 시 RLS를 우회합니다.
4. `volume_snapshots_latest` 뷰는 가장 최근 배치의 레코드만 노출합니다. 웹 API는 이 뷰를 조회해 추가 필터링 없이 최신 데이터를 얻습니다.

> 대용량 데이터를 더욱 세밀하게 다루려면 `batch_id`를 기준으로 직접 페이지네이션하는 전략도 고려할 수 있습니다.

## 웹 애플리케이션

- FastAPI와 Uvicorn으로 구성되며 `/api/volume-changes`에서 최신 배치의 데이터를 백분율 내림차순으로 제공하고, 페이지 크기는 기본 100행(최대 200행)입니다.
- 루트 경로(`/`)는 간단한 UI를 렌더링하여 거래량 급증 종목을 강조하고, KST/UTC 기준 수집 시각을 표시합니다.

### 로컬 개발

```bash
python -m pip install -r web/requirements.txt
export SUPABASE_URL=...
export SUPABASE_SERVICE_ROLE_KEY=...
uvicorn web.app.main:app --reload
```

브라우저에서 `http://127.0.0.1:8000`에 접속합니다.

### Docker 및 Azure 배포

컨테이너 빌드:

```bash
docker build -t stock-alarm-web .
```

로컬 실행:

```bash
docker run --rm -p 8000:8000 \
  -e SUPABASE_URL=... \
  -e SUPABASE_SERVICE_ROLE_KEY=... \
  stock-alarm-web
```

Azure App Service(Web App for Containers)에 배포하려면:

1. 이미지를 Azure Container Registry 또는 Docker Hub에 푸시합니다.
2. Web App에서 이미지를 가져오도록 설정하고 필요한 환경 변수를 입력합니다.
3. 시작 명령은 기본값(`uvicorn web.app.main:app --host 0.0.0.0 --port 8000`)을 그대로 사용하거나 Dockerfile의 CMD를 따릅니다.

Supabase 자격 증명은 서버 측 환경 변수로 관리되고, 브라우저는 FastAPI 엔드포인트만 호출합니다.

## 시간대 주의 사항

- Yahoo Finance의 일봉 데이터는 UTC 기준으로 확정되며, 미국 거래일의 `last_trade_date`가 최신 장 마감 날짜를 가리키지만 공개 시점이 지연될 수 있습니다.
- 파이프라인은 `fetched_at_utc`와 `fetched_at_kst`를 모두 저장해 운영자의 현지 시간과 UTC를 함께 제공합니다.
- 주말/공휴일에는 직전 거래일 데이터가 반복되어 반환될 수 있으며, 유효한 두 개의 거래량 값 또는 0이 아닌 값이 확보되지 않으면 해당 티커는 배치에서 제외됩니다.

## 페이지네이션 전략

- 기본 키 `id BIGSERIAL`을 사용해 `LIMIT 100 OFFSET ...` 형태의 페이지네이션이 가능하며, 최신 배치 내에서 `volume_change_pct DESC NULLS LAST` 정렬을 적용합니다.
- API 응답에는 `has_next`와 `has_previous` 플래그가 포함되어 클라이언트가 페이지 이동 여부를 판단할 수 있습니다.

## 급증 종목 강조

`is_spike`가 `True`인 레코드는 UI에서 별도 배경과 강조 색상을 사용해 2배 이상 급증한 거래량을 한눈에 볼 수 있도록 합니다. 필요 시 백분율 값을 활용해 다른 임계값도 클라이언트 측에서 계산할 수 있습니다.

## 운영 팁

- Yahoo Finance는 요청 빈도 제한을 두고 있습니다. 기본 200개 배치를 처리하며, 배치마다 10초 대기하고 `Too Many Requests`가 감지되면 5분→10분→20분 순으로 최대 세 번 재시도합니다. 이후에도 해소되지 않으면 부분 결과만 업로드하고 프로세스를 종료합니다.
- 공휴일 이후처럼 데이터가 누락되는 경우 `YF_PERIOD`를 `7d` 이상으로 늘려 최소 두 개의 유효 캔들이 수집되도록 할 수 있습니다.
- GitHub Actions 실행 시간이 60분을 넘지 않도록 주기적으로 확인하고, 필요 시 청크 크기를 줄이거나 작업을 병렬화합니다.

## 향후 확장 아이디어

- 과거 급증 기록을 누적해 추세를 분석하는 기능
- Supabase 트리거 등을 활용한 이메일/문자 알림 서비스
- 내부용으로 전환 시 인증/인가 레이어 추가
