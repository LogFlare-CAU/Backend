
# LogFlare Backend

## 실행 방법
### 1. 개발 환경 설정
Python 3.12 환경에서 개발중입니다.
```shell
pip install -r requirements.txt
```

### 2. Alembic 환경 구성
1. `app/alembic` 으로 이동합니다.
2. alembic 을 initialize 합니다.
    ```shell
   alembic init migrations
    ```
   이때 `migrations` 대신 원하는 폴더 명을 입력합니다.
3. `env.py.copy` 파일을 사용하여 `migrations` 내부에 있는 `env.py` 파일을 덮어씁니다.

### 3. DB 생성
Alembic 을 사용하여 DB를 생성합니다. 기본 DB 경로는 `app/db` 이며 이는 `alembic.ini` 파일에서 변경 가능합니다.
```shell
alembic revision --autogenerate
alembic upgrade head
```


### 0. 실행
추후에 `.env` 파일 추가 및 그에 대한 설명 작성 예정

## 디렉토리 및 프로젝트 구조 설명
### `COMMON`
백엔드에서 전역적으로 사용되는 변수 및 함수 모임입니다.

### `ROUTES`
사실상 기능을 하는 디렉토리이며, 모든 기능은 여기에서 구현합니다.   

| 파일명              | 용도                                                            |
|------------------|---------------------------------------------------------------|
| `model.py`       | db orm 선언                                                     |
| `schema.py`      | DTO 선언                                                        |   
| `service.py`     | DB의 입출력 로직 담당 (CRUD)                                          |   
| `application.py` | `service` 만 사용시 책임이 너무 커질때 사용합니다.    예를 들어 외부 api 와의 소통 등을 할때 |
| `router.py`      | api 엔드포인트 선언                                                  |


## 알아두면 유용한 정보
### API의 응답 형식
```json
{
  "success": true,
  "message": "success",
  "error_code": 0,
  "data": {}
}
  ```

모든 응답이 이 형식으로 반환됩니다.
- `success` 를 검사하는것으로 요청 상태를 알 수 있습니다.
- `data` 부분에 실제 응답이 들어갑니다.

### Swagger 용 Template 생성
```python
from common.schema import make_named_response
from typing import Sequence
from .model import User

UserResponse = make_named_response(User, "UserResponse")
UserSequenceResponse = make_named_response(Sequence[User], "UserSequenceResponse")
```


```python
from . import schema
from common.schema import response_maker

@router.get("/", response_model=schema.UserResponse, responses=response_maker([404, 403]))
async def get_users(request: Request):
    return APIResponse
```
- `make_named_response` 함수는 sqlalchemy orm  객체를 swagger 에서 볼 수 있는 DTO 로 변환합니다.
- `response_model` 에 응답 형식을 지정하는것으로 깔끔하게 볼 수 있습니다.
- `response_maker` 를 사용하면 쉽게 에러 정보들을 포함시킬 수 있습니다.
