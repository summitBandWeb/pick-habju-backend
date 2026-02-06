# Pick Habju Backend (픽합주 백엔드)

![Python Version](https://img.shields.io/badge/python-3.12%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi)
![Supabase](https://img.shields.io/badge/Supabase-Database-3ECF8E?logo=supabase)
![Playwright](https://img.shields.io/badge/Playwright-1.56%2B-009688?logo=playwright)

**합주실 예약 가능 여부 확인 서비스**  
사용자가 원하는 합주실의 실시간 예약 가능 여부를 확인하고, 네이버 예약 시스템 연동을 통해 편리한 예약 경험을 제공하는 백엔드 API 서버입니다.

## 📝 프로젝트 배경 (Project Background)

합주실 예약 시 플랫폼마다 흩어져 있는 예약 정보를 확인하기 번거롭다는 문제를 해결하기 위해 시작되었습니다. 본 프로젝트는 다양한 합주실 예약 정보를 통합하여 실시간으로 제공함으로써 사용자의 탐색 비용을 줄이는 것을 목표로 합니다.

## ✨ Key Features (주요 기능)

- [x] **실시간 예약 가능 여부 조회**: 네이버 예약 시스템 연동을 통한 실시간 데이터 수집
- [x] **합주실 즐겨찾기**: 사용자 기기 기반(Device ID) 관심 지점 관리
- [x] **지도 기반 검색**: 위경도 데이터를 활용한 합주실 위치 정보 제공
- [x] **표준화된 API 응답**: Envelope Pattern을 적용하여 일관된 성공/실패 응답 구조 제공
- [x] **확장 가능한 아키텍처**: Service Layer 패턴과 Crawler Registry를 통한 유연한 기능 확장
- [x] **API 문서 자동화**: Swagger UI 및 ReDoc을 통한 실시간 API 명세 제공

## 🛠️ 기술 스택 (Tech Stack)

| Category | Technology | Description |
| --- | --- | --- |
| **Language** | Python 3.12+ | 최신 Python 문법 및 타입 힌트 활용 |
| **Framework** | FastAPI | 고성능 비동기 웹 프레임워크 |
| **Database** | Supabase (PostgreSQL) | 합주실 메타 데이터 및 즐겨찾기 관리 |
| **Crawling** | Playwright / GraphQL / HTTPX | 네이버 지도/예약 크롤링 & 고성능 HTTP 클라이언트 |
| **AI / LLM** | Google Gemini / Ollama | (선택) 데이터 분석 및 로컬/클라우드 LLM 활용 |
| **Security** | SlowAPI | API Rate Limiting (요청 제한) |
| **Testing** | Pytest | 단위 테스트 및 통합 테스트 프레임워크 |
| **VCS** | Git / GitHub | 버전 관리 및 협업 |

---

## 📂 디렉토리 구조 (Directory Structure)

프로젝트의 핵심 코드는 `app/` 디렉토리에 위치하며, 기능별로 모듈화되어 있습니다.  
*(아래 구조는 주요 모듈 및 파일 위주로 요약되었습니다.)*

```
pick-habju-backend/
├── .github/                # GitHub Actions (CI/CD) 설정
├── app/                    # 애플리케이션 핵심 로직
│   ├── api/                # API 라우터 (Controller 역할)
│   │   ├── _dev/           # 개발 및 디버깅용 API 엔드포인트
│   │   ├── available_room.py   # 예약 가능 여부 조회 API
│   │   ├── favorites.py        # 즐겨찾기 관리 API
│   │   └── dependencies.py     # 의존성 주입 (Dependency Injection)
│   ├── core/               # 프로젝트 설정 및 공통 모듈
│   │   ├── config.py           # 환경 변수 및 앱 설정
│   │   ├── error_codes.py      # 전역 에러 코드 정의
│   │   ├── response.py         # 공통 응답 포맷 (Envelope) 정의
│   │   ├── supabase_client.py  # Supabase 클라이언트 설정
│   │   └── limiter.py          # API Rate Limiter
│   ├── crawler/            # 크롤링 모듈 (핵심 기능)
│   │   ├── base.py             # 크롤러 베이스 추상 클래스
│   │   ├── dream_checker.py    # Dream 플랫폼 전용 크롤러
│   │   ├── groove_checker.py   # Groove 플랫폼 전용 크롤러
│   │   ├── naver_checker.py    # Naver 플랫폼 예약 가능 여부 체커
│   │   ├── naver_map_crawler.py # 네이버 지도 검색 및 목록 수집
│   │   └── registry.py          # 크롤러 등록 및 싱글톤 레지스트리
│   ├── exception/          # 사용자 정의 예외 처리
│   │   ├── base_exception.py   # 예외 기본 클래스
│   │   └── envelope_handlers.py# 전역 에러 핸들러 (표준 응답 변환)
│   ├── models/             # 데이터 모델 (Pydantic DTO)
│   │   ├── dto.py              # 주요 요청/응답 DTO
│   │   └── favorite.py         # 즐겨찾기 관련 데이터 모델
│   ├── repositories/       # 데이터 액세스 계층 (DB 통신)
│   │   ├── base.py             # Repository 인터페이스
│   │   └── supabase_repository.py 
│   ├── services/           # 비즈니스 로직 계층
│   │   ├── availability_service.py # 통합 예약 가능 여부 조회
│   │   └── room_parser_service.py  # 룸 데이터 파싱 및 가공
│   ├── utils/              # 공용 유틸리티
│   │   ├── room_loader.py      # DB 데이터 로드 유틸리티
│   │   ├── room_router.py      # 플랫폼별 룸 라우팅 로직
│   │   └── client_loader.py    # 비동기 HTTP 클라이언트 관리
│   ├── validate/           # 유효성 검증 로직
│   │   ├── request_validator.py# API 요청 파라미터 검증
│   │   └── hour_validator.py   # 시간 포맷 및 범위 검증
│   └── main.py             # FastAPI 애플리케이션 진입점
├── scripts/                # 배포 및 데이터 수집 스크립트
├── tests/                  # 테스트 코드 (Pytest)
├── .env.example            # 환경 변수 템플릿
├── requirements.txt        # 의존성 목록
└── README.md               # 프로젝트 설명서
```

---

## 🏗️ 아키텍처 (Architecture)

이 프로젝트는 유지보수성과 확장성을 위해 **Layered Architecture (계층형 아키텍처)** 패턴을 따르고 있습니다.
각 계층은 관심사 분리(Separation of Concerns) 원칙에 따라 명확한 역할을 가지며, 상위 계층은 하위 계층에만 의존합니다.

### 데이터 흐름 (Data Flow)

`API Layer` (요청 처리, Controller) → `Service Layer` (비즈니스 로직) → `Data Access Layer` (DB/크롤링)

### 각 계층의 역할과 위치

| Layer | Directory | Description |
| --- | --- | --- |
| **Presentation (API)** | `app/api/` | - 클라이언트 요청(Request)을 받아 유효성을 검증하고 응답(Response)을 반환합니다.<br>- 비즈니스 로직을 직접 수행하지 않고 Service 계층에 위임합니다.<br>- **Dependency Injection (DI)** 을 통해 Service 객체를 주입받습니다. |
| **Business Logic (Service)** | `app/services/` | - 애플리케이션의 핵심 비즈니스 로직을 수행합니다.<br>- 여러 Repository나 Crawler를 조합하여 데이터를 가공합니다.<br>- 예: `AvailabilityService`는 여러 플랫폼의 크롤러를 병렬로 실행하고 결과를 집계합니다. |
| **Data Access (Repository)** | `app/repositories/`<br>`app/crawler/` | - 데이터베이스(Supabase)나 외부 시스템(네이버 지도)과 직접 통신합니다.<br>- DB 쿼리 실행 또는 웹 크롤링을 담당하며, 순수한 데이터 객체(DTO)를 반환합니다. |
| **Domain Model** | `app/models/` | - 계층 간 데이터 전달을 위한 Pydantic 모델(DTO)을 정의합니다. |

---

## 📡 주요 API 엔드포인트 (Key API Endpoints)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/rooms/availability` | `GET` | 지도 기반 합주실 및 예약 가능 여부 조회 |
| `/api/favorites` | `GET` | 사용자의 즐겨찾기 목록 조회 |
| `/api/favorites` | `POST` | 특정 합주실을 즐겨찾기에 추가 |
| `/api/favorites` | `DELETE` | 즐겨찾기 항목 삭제 |

> 상세한 API 명세는 서버 실행 후 [Swagger UI](http://127.0.0.1:8000/docs)에서 확인할 수 있습니다.

---

## 🚀 시작 가이드 (Getting Started)

로컬 개발 환경을 설정하고 서버를 실행하는 방법입니다.

### 1-1. 프로젝트 클론
```bash
git clone https://github.com/summitBandWeb/pick-habju-backend.git
cd pick-habju-backend
```

### 1-2. 가상환경 생성 및 활성화

**Windows (PowerShell)**
```powershell
# 가상환경 생성 (venv 대신 다른 이름 사용 시 .gitignore에 추가 필요)
python -m venv venv

# 가상환경 활성화(venv는 가상환경 이름)
.\venv\Scripts\Activate.ps1
```

**Mac/Linux**
```bash
# 가상환경 생성
python3 -m venv venv

# 가상환경 활성화
source venv/bin/activate
```

### 2. 패키지 설치
**가상환경 활성화 후** `requirements.txt`에 명시된 필수 라이브러리를 설치합니다.

```bash
pip install -r requirements.txt
```

### 3. Playwright 브라우저 설치
네이버 지도 크롤링을 위해 Playwright 브라우저 바이너리를 설치해야 합니다.

```bash
playwright install chromium
```

### 4. 환경 변수 설정
프로젝트 루트의 `.env.example` 파일을 복사하여 `.env` 파일을 생성하고, 필요한 값을 설정합니다.
(**구체적인 환경변수 값은 팀 노션 페이지를 참고하세요.**)

```bash
cp .env.example .env
```

```ini
# .env 예시
ENV=dev
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
NAVER_MAP_URL=https://map.naver.com
```

### 5. 서버 실행

```bash
# 개발 모드 (코드 수정 시 자동 재시작)
uvicorn app.main:app --reload
```

서버가 실행되면 아래 주소에서 API 문서를 확인할 수 있습니다.
- Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## 🧪 테스트 실행

`pytest`를 사용하여 작성된 테스트 코드를 실행할 수 있습니다.

```bash
# 전체 테스트 실행
pytest

# 특정 파일 테스트 실행
pytest tests/api/test_available_room.py
```

---

## 🛠️ 트러블슈팅 (Troubleshooting)

### 1. Playwright 실행 오류
- **현상**: 크롤링 작업 시 브라우저 바이너리 부족 에러 발생
- **해결**: `playwright install chromium` 명령어를 통해 필수 브라우저를 설치하세요.

### 2. Supabase 연결 오류
- **현상**: 데이터 조회 시 `APIError` 또는 연결 타임아웃 발생
- **해결**: `.env` 파일의 `SUPABASE_URL`과 `SUPABASE_KEY`가 정확한지 확인하고, 로컬 네트워크 환경(방화벽 등)을 점검하세요.

---

## 🤝 기여 가이드 (Contribution Guide)

1. **이슈 생성**: 새로운 기능 개발이나 버그 수정 시작 전, 이슈를 생성하여 의도를 공유합니다.
2. **브랜치 생성**: 규칙에 맞는 브랜치를 생성합니다 (예: `feat/130-description`).
3. **코드 작성 및 테스트**: 기능을 구현하고 적절한 테스트 코드를 작성합니다.
4. **Pull Request**: 작업 완료 후 PR을 생성하며, 팀원 1명 이상의 승인이 필요합니다.
5. **커밋 메시지**: 하단의 [협업 컨벤션](#-협업-컨벤션-convention)을 엄격히 준수합니다.

---

## 🤝 협업 컨벤션 (Convention)

- **Commit Message**: [Conventional Commits](https://www.conventionalcommits.org/) 규칙을 따릅니다.
    (자세한 내용은 팀 노션 및 [CONVENTION.md](CONVENTION.md) 파일을 참고하세요.)
    - `feat`: 새로운 기능 추가
    - `fix`: 버그 수정
    - `docs`: 문서 수정
    - `refactor`: 코드 리팩토링
    - `test`: 테스트 코드 추가/수정
- **Branch Strategy**: Git Flow 변형 (main, dev, feat/*)

## 🗄️ 데이터베이스 구조 (Database Schema)

Supabase (PostgreSQL)를 사용하여 합주실 데이터와 사용자 즐겨찾기 정보를 관리합니다.

![Database ERD](docs/images/supabase_erd(260206).png)

### 주요 테이블 설명

| Table | Description | Key Columns |
| --- | --- | --- |
| `branch` | 합주실 지점 정보 (예: XX합주실 홍대점) | `business_id` (PK), `name`, `lat`, `lng` |
| `room` | 지점 내 개별 룸 정보 (예: A룸, B룸) | `biz_item_id` (PK), `business_id` (FK), `price_per_hour`, `max_capacity` |
| `favorites` | 사용자 즐겨찾기 목록 | `device_id` (UUID), `biz_item_id` (FK), `created_at` |

- **관계 (Relationships)**:
    - `branch` (1) : `room` (N) -> 하나의 지점은 여러 개의 룸을 가집니다.
    - `room` (1) : `favorites` (N) -> 하나의 룸은 여러 사용자에 의해 즐겨찾기 될 수 있습니다. 
    - (참고: `favorites`는 `device_id`를 통해 비로그인 사용자도 기기 기반으로 식별합니다.)
