## 📐 전체 아키텍처

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   클라이언트    │ ──▶ │  Cloudflare  │ ──▶ │  Cloud Run   │ ──▶ │   Supabase   │
│   (앱/웹)     │     │  (CDN/WAF)   │     │  (API 서버)   │     │  (PostgreSQL)│
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
```

## ☁️ Google Cloud Platform (GCP)

### 사용 서비스

| 서비스                | 용도                       |
| --------------------- | -------------------------- |
| **Cloud Run**         | 컨테이너화된 API 서버 실행 |
| **Artifact Registry** | Docker 이미지 저장소       |
| **Cloud Logging**     | 로그 수집/모니터링         |

### 배포 프로세스

```
GitHub Push → GitHub Actions → Docker Build → Artifact Registry → Cloud Run 배포
```

- **Prod**: `main` 브랜치 푸시 시 자동 배포
- **Alpha**: `dev` 브랜치 푸시 시 자동 배포

### 인증 방식

- **Workload Identity Federation (WIF)**: Service Account Key 대신 WIF 사용
- GitHub Actions에서 GCP 리소스에 안전하게 접근

---

## 🔶 Cloudflare

### 역할

| 기능           | 설명                            |
| -------------- | ------------------------------- |
| **DNS**        | 도메인 → Cloud Run 라우팅       |
| **CDN**        | 정적 리소스 캐싱 (API는 Bypass) |
| **SSL/TLS**    | HTTPS 인증서 관리               |
| **WAF**        | 웹 애플리케이션 방화벽          |
| **Rate Limit** | 과도한 요청 차단 (DDoS 방어)    |

### 핵심 설정

| 항목         | 설정값                |
| ------------ | --------------------- |
| **SSL 모드** | Full (Strict)         |
| **API 캐시** | Bypass (`/api/*`)     |
| **프록시**   | Proxied (주황색 구름) |

### DNS 구조

```
alpha-api.pickhabju.com  →  CNAME  →  Cloud Run URL
    └─ Cloudflare Worker가 Host 헤더 변환
```

---

## 🗄️ Supabase

### 역할

| 기능              | 설명              |
| ----------------- | ----------------- |
| **PostgreSQL DB** | 메인 데이터베이스 |

### 환경 구성

| 환경      | 용도                     |
| --------- | ------------------------ |
| **Prod**  | 운영 데이터베이스        |
| **Alpha** | 개발/테스트 데이터베이스 |

---

## 🔄 CI/CD 파이프라인

### 배포 흐름

```
┌───────────────────────────────────────────────────────────────────┐
│                        GitHub Actions                             │
├───────────────────────────────────────────────────────────────────┤
│  1. 코드 체크아웃                                                  │
│  2. WIF로 GCP 인증                                                 │
│  3. Docker 이미지 빌드                                             │
│  4. Artifact Registry에 푸시                                       │
│  5. (Prod만) Supabase DB 백업                                      │
│  6. (Prod만) 마이그레이션 적용                                      │
│  7. Cloud Run 배포                                                 │
│  8. Discord 알림 전송                                              │
└───────────────────────────────────────────────────────────────────┘
```

### 워크플로우 파일

| 파일               | 트리거      | 대상         |
| ------------------ | ----------- | ------------ |
| `deploy-test.yaml` | `dev` 푸시  | Alpha 서비스 |
| `deploy-prod.yaml` | `main` 푸시 | Prod 서비스  |
