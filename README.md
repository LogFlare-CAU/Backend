<h1 align="center">🚀 LogFlare Backend</h1>


<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue?logo=python" alt="Python">
  <img src="https://img.shields.io/badge/FastAPI-0.115+-brightgreen?logo=fastapi" alt="FastAPI">
  <img src="https://img.shields.io/badge/SQLAlchemy-2.x-orange?logo=python" alt="SQLAlchemy">
  <img src="https://img.shields.io/badge/Alembic-Migrations-lightgrey?logo=python" alt="Alembic">
</p>

FastAPI 기반의 백엔드 서버로, 공통 스키마 구조와 응답 형식을 일관되게 유지하는 로깅 중심 RESTful API 프로젝트입니다.
모든 API는 **표준화된 응답 포맷**과 **자동 Swagger 문서화**를 지원합니다.

---

## ⚙️ 실행 방법

### 1. 개발 환경 설정

Python 3.12 환경에서 개발 중입니다.

```bash
pip install -r requirements.txt
```

### 2. Alembic 환경 구성

1. `app/alembic` 으로 이동합니다.
2. Alembic 초기화:

   ```bash
   alembic init migrations
   ```

   `migrations` 대신 원하는 폴더명을 지정해도 됩니다.
3. `env.py.copy` 파일을 사용하여 `migrations/env.py`를 덮어씁니다.

### 3. 데이터베이스 생성

Alembic을 통해 DB를 생성합니다.
기본 DB 경로는 `app/db`이며, 이는 `alembic.ini`에서 수정할 수 있습니다.

```bash
alembic revision --autogenerate
alembic upgrade head
```

### 4. 실행

추후 `.env` 파일 추가 및 환경 변수 설명이 작성될 예정입니다.

---

## 🧩 디렉토리 구조 및 역할

### `COMMON`

백엔드 전역에서 공통으로 사용하는 상수, 함수, 예외, 스키마 등을 포함합니다.

### `ROUTES`

프로젝트의 핵심 기능이 구현된 디렉토리로, 각 API의 세부 로직을 담당합니다.

| 파일명              | 역할 설명                               |
| ---------------- | ----------------------------------- |
| `model.py`       | DB ORM 선언                           |
| `schema.py`      | DTO 선언                              |
| `service.py`     | DB 입출력(CRUD) 로직                     |
| `application.py` | 외부 API 연동 등 복합 로직 (Service보다 상위 개념) |
| `router.py`      | FastAPI 라우터 및 엔드포인트 선언              |

---

## 📡 API 응답 형식

모든 API는 다음과 같은 JSON 형식을 반환합니다.

```json
{
  "success": true,
  "message": "success",
  "error_code": 0,
  "data": {}
}
```

* `success`: 요청 성공 여부
* `message`: 처리 상태 메시지
* `error_code`: 에러 코드 (0이면 정상)
* `data`: 실제 응답 데이터

> → 즉, `success`를 확인하는 것만으로 요청의 성공 여부를 판단할 수 있습니다.

---

## 🧱 Swagger 템플릿 예시

### 응답 DTO 정의

```python
from common.schema import make_named_response
from typing import Sequence
from .model import User

UserResponse = make_named_response(User, "UserResponse")
UserSequenceResponse = make_named_response(Sequence[User], "UserSequenceResponse")
```

### 라우터 정의

```python
from . import schema
from common.schema import response_maker

@router.get("/", response_model=schema.UserResponse, responses=response_maker([404, 403]))
async def get_users(request: Request):
    return APIResponse
```

### 설명

* `make_named_response`: SQLAlchemy ORM 객체를 Swagger에서 읽을 수 있는 DTO로 변환
* `response_model`: Swagger 문서에 명시되는 실제 응답 구조 지정
* `response_maker`: 공통 에러 응답 형식(404, 403 등)을 자동 등록

---

## 🧠 추가 참고

* Swagger UI는 `/docs` 엔드포인트에서 자동 생성됩니다.
* 모든 API는 `common.schema.APIResponse`를 상속하거나 `response_maker`를 통해 일관된 응답을 보장합니다.
