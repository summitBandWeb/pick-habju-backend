# 로깅 및 추적 (Logging & Tracing) 가이드

이 문서는 `pick-habju-backend` 프로젝트의 로깅 시스템 아키텍처, 운영 방법, 그리고 프론트엔드 연동 가이드를 다룹니다.

## 1. 개요

본 프로젝트는 분산 환경에서의 트러블슈팅을 위해 **Trace ID (추적 ID)** 기반의 로깅 시스템을 구축했습니다.
또한 민감 정보(PII, Credential) 유출 방지를 위해 **Log Masking** 기능을 미들웨어 레벨에서 제공합니다.

### 주요 기능
- **Trace ID 생성 및 전파**: 모든 요청에 고유한 UUID v4(`X-Trace-ID`)를 부여하여 요청의 전체 생명주기를 추적합니다.
- **민감 정보 마스킹**: 비밀번호, 토큰, 개인정보 등은 로그 기록 시 자동으로 `***` 처리됩니다.
- **JSON 포맷 로그**: Logstash, Datadog 등 로그 수집 시스템과의 호환성을 위해 JSON 포맷을 사용합니다.
- **로그 파일 보안**: `logs/app.log` 파일은 소유자만 읽을 수 있도록(0600) 권한이 제한됩니다.

---

## 2. 운영 가이드 (Troubleshooting)

### 로그 파일 위치
- 경로: `logs/app.log`
- 로테이션: 매일 자정 기준으로 파일이 분리되며, 최대 7일간 보관됩니다. (예: `app.log.2026-02-13`)

### Trace ID로 로그 검색하기
시스템 장애나 버그 신고 시, 특정 요청의 전체 흐름을 파악하기 위해 Trace ID를 사용합니다.

**Linux/Mac/Git Bash 예시:**
```bash
# 특정 Trace ID(abc-123)가 포함된 모든 로그 검색
grep "trace_id.*abc-123" logs/app.log

# 실시간 로그 모니터링 (JSON 포맷 파싱을 위해 jq 권장)
tail -f logs/app.log | grep --line-buffered "ERROR"
```

**PowerShell 예시:**
```powershell
# 특정 Trace ID 검색
Select-String -Path "logs/app.log" -Pattern "abc-123"

# 최근 에러 로그 확인
Get-Content "logs/app.log" -Tail 100 | Where-Object { $_ -match "ERROR" }
```

---

## 3. 프론트엔드 연동 가이드

프론트엔드(React/Next.js)에서는 백엔드 API 호출 시 `X-Trace-ID`를 응답 헤더에서 추출하여 에러 리포팅에 활용해야 합니다.

### 권장 흐름
1. API 요청 시, 백엔드가 반환하는 `X-Trace-ID` 헤더를 확인합니다.
2. 에러 발생(500 Internal Server Error 등) 시, 사용자에게 "에러가 발생했습니다. (ID: {TraceID})" 와 같이 안내합니다.
3. 사용자가 해당 ID를 고객센터에 제보하면, 개발자는 위 운영 가이드를 통해 로그를 즉시 조회할 수 있습니다.

### Axios Interceptor 예시 코드

```typescript
import axios from 'axios';

const apiClient = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL,
});

// 응답 인터셉터
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // 백엔드에서 전달받은 Trace ID 추출
    const traceId = error.response?.headers['x-trace-id'];
    
    if (traceId) {
      console.error(`[API Error] Trace ID: ${traceId}`, error);
      
      // Sentry 등 에러 모니터링 도구에 태깅
      // Sentry.setTag("trace_id", traceId);
      
      // 사용자에게 보여줄 에러 객체에 ID 포함
      error.traceId = traceId;
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;
```

---

## 4. 유의사항 및 성능 (Performance)

### 마스킹 오버헤드 (Masking Overhead)
- `LogMasker`는 정규식(Regex)을 사용하여 마스킹을 수행합니다.
- 긴 문자열이나 깊은 중첩 구조의 JSON 객체 로깅 시 CPU 오버헤드가 발생할 수 있습니다.
- **최적화**: 깊은 중첩(Depth > 10)이나 순환 참조가 감지되면 재귀 마스킹을 중단하고 문자열로 변환합니다.

### 비동기 로깅 (Async Logging)
- 현재 `TimedRotatingFileHandler`는 동기(Blocking) 방식으로 동작합니다.
- 초당 로그량이 매우 많은 경우(TPS > 1000), 메인 스레드 블로킹을 방지하기 위해 `QueueHandler`나 `QueueListener`를 통한 비동기 로깅 도입을 검토해야 합니다.

### 보안 (Security)
- 로그 파일(`logs/app.log`)은 서버 내에서 **소유자(Owner)** 만 읽기/쓰기가 가능합니다(권한 600).
- `setup_logging` 함수가 애플리케이션 시작 시 이를 자동으로 설정하므로, 권한을 임의로 변경하지 마십시오.
