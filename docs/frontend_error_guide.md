# 🚧 프론트엔드 개발팀을 위한 에러 핸들링 가이드

안녕하세요! 백엔드 팀입니다. 🙇‍♂️
이번에 **API 응답 및 에러 처리를 대대적으로 개편**하게 되어, 변경 배경과 프론트엔드 작업 가이드를 공유드립니다.

---

## 1. 변경 배경 (Why Changed?)

기존에는 에러가 발생했을 때 응답 포맷이 일관되지 않았습니다.
어떤 API는 `detail` 메시지를 주고, 어떤 API는 `error` 필드를 주는 등 혼란이 있었죠.

### 🚫 Before (기존 문제점)
```javascript
// 프론트엔드에서 이렇게 복잡하게 처리해야 했습니다 😫
try {
  await api.post('/room');
} catch (err) {
  if (err.response.data.detail) {
    alert(err.response.data.detail); // Case 1
  } else if (err.response.data.message) {
    alert(err.response.data.message); // Case 2
  } else {
    alert("알 수 없는 오류");
  }
}
```

### ✅ After (기대 효과)
이제 **"모든 에러"**는 단 하나의 통일된 규격(`ApiResponse`)으로 내려갑니다.
성공이든 실패든 항상 같은 봉투(Envelope)에 담겨 옵니다.

---

## 2. 변경된 응답 규격 (Spec)

모든 API 응답(성공/실패 포함)은 아래 JSON 형태를 보장합니다.

```json
{
  "isSuccess": false,          // 성공 여부 (true/false)
  "code": "ROOM_001",          // 에러 코드 (상수)
  "message": "이미 예약된 시간입니다.", // 사용자에게 보여줄 친절한 메시지
  "result": null               // (성공 시 데이터, 실패 시 에러 상세)
}
```

---

## 3. 프론트엔드 작업 가이드 (To-Do)

**"작업하시느라 피곤하시겠지만, 딱 한 번만 수정해두면 앞으로 엄청 편해지실 거예요!"**

개별 컴포넌트나 페이지의 `try-catch` 구문을 일일이 수정하실 필요 **없습니다**.
사용 중이신 HTTP Client (Axios, Fetch 등)의 **Response Interceptor (전역 처리)** 부분만 수정해주세요.

### 예시 (Axios Interceptor)

```javascript
// axiosInstance.js (또는 api 설정 파일)

instance.interceptors.response.use(
  (response) => {
    // 성공 응답 (isSuccess: true)
    return response;
  },
  (error) => {
    // 1. 서버에서 내려준 표준 포맷이 있는지 확인
    if (error.response && error.response.data) {
      const { isSuccess, message, code, result } = error.response.data;

      // 2. 표준 포맷이라면, 그대로 메시지를 사용 (단, 인증 에러 등은 별도 처리)
      if (isSuccess === false) {
        console.error(`[Error] ${code}: ${message}`);
        
        // (선택) 사용자에게 알림
        // toast.error(message); 
        
        // (중요) 필요하다면 여기서 에러를 throw하여 개별 컴포넌트가 추가 처리를 하게 함
        // return Promise.reject(new Error(message));
      }
    }

    // 3. 네트워크 오류 등 예상치 못한 케이스
    return Promise.reject(error);
  }
);
```

### ✨ 장점
1.  **예외 처리 코드 삭제**: 컴포넌트마다 `if (err.detail) ...` 하던 코드를 싹 지우셔도 됩니다.
2.  **자동 메시지**: 백엔드에서 내려주는 `message` 필드는 기획팀과 합의된 "사용자 친화적 메시지"입니다. 그대로 `alert`나 `toast`에 띄우시면 됩니다.
3.  **Validation 처리**: 입력값 검증 실패 시 `result` 필드에 `{"fieldName": "error msg"}` 형태로 상세히 내려드리니, 폼 에러 표시에 활용하세요.

---

이번 변경으로 잠시 번거로우시겠지만, 앞으로의 개발 속도와 안정성을 위한 **'지반 다지기'** 작업이니 너른 양해 부탁드립니다. 🙏
문의사항은 언제든 편하게 말씀해주세요!
