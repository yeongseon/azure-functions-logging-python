# Azure Functions Logging

> **Azure Functions Python DX Toolkit**의 일부 — [azure-functions-cookbook-python](https://github.com/yeongseon/azure-functions-cookbook-python)에서 도그푸딩(dogfooding)으로 검증되었습니다.

[![PyPI](https://img.shields.io/pypi/v/azure-functions-logging.svg)](https://pypi.org/project/azure-functions-logging/)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://pypi.org/project/azure-functions-logging/)
[![CI](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/ci-test.yml/badge.svg)](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/ci-test.yml)
[![Release](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/publish-pypi.yml)
[![Security Scans](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/security.yml/badge.svg)](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/security.yml)
[![codecov](https://codecov.io/gh/yeongseon/azure-functions-logging-python/branch/main/graph/badge.svg)](https://codecov.io/gh/yeongseon/azure-functions-logging-python)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://pre-commit.com/)
[![Docs](https://img.shields.io/badge/docs-gh--pages-blue)](https://yeongseon.github.io/azure-functions-logging-python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

다른 언어로 보기: [English](README.md) | [日本語](README.ja.md) | [简体中文](README.zh-CN.md)

**Azure Functions Python v2를 위한 호출(invocation) 인지 가능한 관측성(observability).**
`invocation_id`를 노출하고, cold start를 감지하며, `host.json` 설정 오류를 경고하고, Application Insights에 바로 사용 가능한 구조화된 로그를 출력합니다 — Python 표준 `logging`을 대체하지 않습니다.

---

**Azure Functions Python DX Toolkit**의 일부
→ FastAPI와 같은 개발자 경험을 Azure Functions에 제공합니다.

## 왜 필요한가

Azure Functions Python의 logging에는 일반 logging 라이브러리가 다루지 않는 고유의 실패 모드가 있습니다:

| 문제 | 발생 현상 | 이 라이브러리의 해결책 |
|------|-----------|------------------------|
| `host.json` 로그 레벨 충돌 | `INFO` 로그가 Azure에서 조용히 사라짐 | 시작 시점에 감지하여 경고 |
| 로그에 `invocation_id` 부재 | 특정 실행과 로그를 연결할 수 없음 | `context` 객체에서 자동 주입 |
| Cold start가 보이지 않음 | 새 worker 인스턴스 시작 시 신호 없음 | 첫 `inject_context()` 호출 시 자동 감지 |
| 시끄러운 서드파티 로거 | `azure-core`, `urllib3` 등이 Application Insights를 채움 | `SamplingFilter` / `RedactionFilter` |
| 로컬과 클라우드 출력 불일치 | 색상 출력이 프로덕션 파이프라인을 깨뜨림 | 환경 인지 포매터 자동 전환 |
| PII가 로그에 유출 | extra 필드를 통해 민감 값이 우발적으로 기록 | 키 기반 redaction을 수행하는 `RedactionFilter` |

## 무엇을 하는가

- **호출 컨텍스트** — 모든 로그에 `invocation_id`, `function_name`, `cold_start`를 자동 주입
- **구조화된 JSON 출력** — Application Insights에 바로 적합한 NDJSON 포맷
- **노이즈 제어** — `SamplingFilter`로 시끄러운 서드파티 로거의 비율을 제한
- **PII 보호** — `RedactionFilter`로 민감 필드를 로그 집계에 도달하기 전에 마스킹

> **범위 면책.** 이 패키지는 Python `logging` / stdout으로 구조화된 JSON을 씁니다. Application Insights에서 어떻게 표시되는지는 Azure Functions host, worker, logging 구성, ingestion 파이프라인에 따라 달라집니다. 라이브러리는 ingestion이나 schema mapping을 책임지지 않습니다 — `customDimensions`로 파싱되는 형태와 raw `message`에 들어가는 형태 모두 프로덕션에서 유효합니다.

## Before / After

`azure-functions-logging` **사용 전** — 단순 `print()` 출력, 컨텍스트 없음, 구조 없음:

```python
import azure.functions as func

app = func.FunctionApp()


@app.route(route="orders")
def process_order(req: func.HttpRequest) -> func.HttpResponse:
    print("Processing order")        # invocation_id 없음, 구조 없음
    print(f"Order: {req.get_json()}")  # PII 유출 가능, 로그 레벨 없음
    return func.HttpResponse("OK")
```

터미널 출력:

```
Processing order
Order: {'customer': 'Alice', 'total': 99.99}
```

> Invocation ID 없음. 로그 레벨 없음. Application Insights에서 상관(correlate)하기 어려움.

`azure-functions-logging` **사용 후** — 구조화되고, 쿼리 가능하며, 프로덕션 준비 완료:

```python
import azure.functions as func

from azure_functions_logging import get_logger, logging_context, setup_logging

setup_logging()
logger = get_logger(__name__)
app = func.FunctionApp()


@app.route(route="orders")
def process_order(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):
        logger.info("Processing order", order_id="o-999")
        return func.HttpResponse("OK")
```

로컬 터미널 출력 (색상 적용):

```
10:30:00 INFO     function_app  Processing order  [invocation_id=abc-123-def, function_name=process_order, cold_start=true]
```

프로덕션 출력 (Application Insights용 NDJSON):

```json
{"timestamp": "2024-01-15T10:30:00+00:00", "level": "INFO", "logger": "function_app",
 "message": "Processing order", "invocation_id": "abc-123-def",
 "function_name": "process_order", "trace_id": null, "cold_start": true,
 "exception": null, "extra": {"order_id": "o-999"}}
```

> 모든 로그에 `invocation_id`와 `cold_start`가 포함됩니다. Application Insights에서 쿼리 가능. `print()` 문 없음.

> **참고:** 정확한 Application Insights 스키마는 ingestion 파이프라인에 따라 다릅니다. 일부 배포에서는 JSON 필드가 `customDimensions`로 파싱되고, 다른 곳에서는 JSON이 `message` 컬럼 내부에 그대로 남습니다. 두 형태 모두에 대한 예시가 아래에 있습니다.

### Application Insights에서 쿼리

#### JSON 필드가 `customDimensions`로 파싱되는 경우

```kql
traces
| where customDimensions.invocation_id == "abc-123-def"
| project timestamp, message, customDimensions.cold_start, customDimensions.function_name
| order by timestamp asc
```

지난 1시간의 모든 cold start 찾기:

```kql
traces
| where customDimensions.cold_start == "true"
| where timestamp > ago(1h)
| summarize count() by bin(timestamp, 5m)
```

#### JSON이 `message` 컬럼에 그대로 남는 경우

```kql
traces
| extend payload = parse_json(message)
| where tostring(payload.invocation_id) == "abc-123-def"
| project timestamp, tostring(payload.message), tostring(payload.cold_start), tostring(payload.function_name)
| order by timestamp asc
```

지난 1시간의 모든 cold start 찾기:

```kql
traces
| extend payload = parse_json(message)
| where tostring(payload.cold_start) == "true"
| where timestamp > ago(1h)
| summarize count() by bin(timestamp, 5m)
```

## 이 패키지가 하지 않는 일

이 패키지는 다음을 책임지지 않습니다:

- **stdlib logging 대체** — Python 표준 `logging`을 감싸고 보강할 뿐, 절대 대체하지 않습니다
- **분산 트레이싱** — end-to-end trace 상관에는 OpenTelemetry나 Application Insights SDK를 사용하세요
- **API 문서** — API 문서 및 spec 생성에는 [`azure-functions-openapi`](https://github.com/yeongseon/azure-functions-openapi-python)를 사용하세요

## 설치

```bash
pip install azure-functions-logging
```

## Quick Start

```python
import azure.functions as func
from azure_functions_logging import get_logger, logging_context, setup_logging

setup_logging()
logger = get_logger(__name__)

app = func.FunctionApp()

@app.route(route="hello")
def hello(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):  # invocation_id, function_name, cold_start 바인딩 후, 종료 시 복원
        logger.info("Request received")
        # {"level": "INFO", "invocation_id": "abc-123", "cold_start": true, ...}

        return func.HttpResponse("OK")
```

`logging_context`는 권장되는 기본 패턴입니다. 진입 시 컨텍스트를 주입하고, **항상** 종료 시 (핸들러가 예외를 발생시키더라도) 이전 컨텍스트를 복원하므로, 재사용되는 worker에서 stale 컨텍스트가 다음 호출로 누출되는 것을 방지합니다.

저수준 제어가 필요하거나 커스텀 미들웨어와 통합할 때는 토큰 기반 복원을 사용하세요:

```python
tokens = inject_context(context)
try:
    logger.info("Request received")
finally:
    restore_context(tokens)
```

`reset_context()`는 의도적으로 모든 컨텍스트를 지우려는 경우(예: 테스트 teardown)에만 사용하세요.

Functions host를 로컬에서 실행 ([e2e 예제 앱](examples/e2e_app) 사용):

```bash
func start
```

### 로컬 및 Azure에서 검증

배포 후 ([docs/deployment.md](docs/deployment.md) 참고), 동일한 요청은 두 환경에서 동일한 응답을 생성합니다.

#### 로컬

```bash
curl -s http://localhost:7071/api/logme?correlation_id=demo-123
```

```json
{"logged": true, "correlation_id": "demo-123"}
```

#### Azure

```bash
curl -s "https://<your-app>.azurewebsites.net/api/logme?correlation_id=demo-123"
```

```json
{"logged": true, "correlation_id": "demo-123"}
```

> koreacentral 리전의 임시 Azure Functions 배포로 검증되었습니다 (Python 3.12, Consumption plan). 응답은 캡처되었으며 URL은 익명화되었습니다.

## 호출 컨텍스트 (Invocation Context)

핸들러가 실행되는 동안 호출 컨텍스트를 바인딩하려면 `logging_context()`를 사용하세요. 다음을 설정합니다:

- `invocation_id` — 실행마다 고유, 한 요청의 모든 로그를 상관시킴
- `function_name` — Azure Functions 함수 이름
- `trace_id` — 플랫폼의 trace 컨텍스트. 유효한 W3C `traceparent` 헤더에서만 추출되며, 유효성 검증이 엄격하여 잘못된 값은 무시됩니다
- `cold_start` — 이 worker 프로세스의 첫 호출일 때 `True`

> **`cold_start` 의미.** `cold_start=True`는 *모듈 로드 후 이 Python worker 프로세스에서 관측된 첫 호출*을 의미합니다. **플랫폼 레벨**의 cold start 메트릭이 아니며, Azure Functions 메트릭이 보고하는 App Service plan / instance 할당 cold start와는 일치하지 않습니다. 같은 worker의 후속 호출은 worker가 재활용될 때까지 `cold_start=False`를 발행합니다.

```python
def my_function(req, context):
    with logging_context(context):
        logger.info("handler started")
        # 이 시점부터의 모든 로그에 invocation_id와 cold_start 포함
```

저수준 제어 (예: 미들웨어)에는 `inject_context()`와 `restore_context()`를 사용하세요:

```python
tokens = inject_context(context)
try:
    logger.info("handler started")
finally:
    restore_context(tokens)
```

컨텍스트 주입이 없으면 모든 로그 라인에서 이 필드들은 `None`입니다.

### `with_context` 데코레이터

보일러플레이트를 줄이려면, `inject_context()`를 수동으로 호출하는 대신 `with_context` 데코레이터를 사용하세요:

```python
import azure.functions as func
from azure_functions_logging import get_logger, setup_logging, with_context

setup_logging()
logger = get_logger(__name__)

app = func.FunctionApp()

@app.route(route="hello")
@with_context
def hello(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    logger.info("Request received")
    return func.HttpResponse("OK")
```

데코레이터는 이름으로 `context` 매개변수를 찾고, 핸들러 실행 전 `inject_context()`를 호출하며, 반환 후 `finally`에서 컨텍스트 변수를 리셋합니다.

커스텀 매개변수 이름:

```python
@with_context(param="ctx")
def hello(req: func.HttpRequest, ctx: func.Context) -> func.HttpResponse:
    ...
```

동기 및 비동기 핸들러가 모두 지원됩니다.

### 글로벌 LogRecordFactory (opt-in)

`setup_logging()` 이후에 핸들러가 추가될 수 있거나, 핸들러/필터 구성과 무관하게 **모든** `LogRecord`에 호출 컨텍스트를 적용하고 싶은 애플리케이션에서는, 시작 시 글로벌 컨텍스트 팩토리를 한 번 설치하세요:

```python
from azure_functions_logging import install_context_factory, setup_logging

install_context_factory()  # record 생성 시점에 컨텍스트 주입
setup_logging()
```

활성화되면 `invocation_id`, `function_name`, `trace_id`, `cold_start`는 예약된 `LogRecord` 속성이 됩니다. stdlib `extra=`를 통해 이들을 전달하면 `KeyError`가 발생합니다. 키를 자동으로 정제하는 `FunctionLogger`를 사용하거나 다른 키 이름을 선택하세요.

> **`setup_logging()`과의 관계:** `setup_logging()`은 기본적으로 핸들러에 `ContextFilter`를 설치합니다. 둘 다 호출해도 됩니다 — 동일한 값을 설정하므로 충돌이 없습니다. `install_context_factory()`는 나중에 추가되는 핸들러나 필터 체인을 우회하는 로거에서도 적용됨을 보장합니다.

## 구조화된 JSON 출력 (프로덕션)

로그가 Application Insights나 어떤 집계 시스템으로 흘러갈 때는 JSON 포맷을 사용하세요:

> **참고:** `format` 매개변수는 이 라이브러리가 생성한 핸들러 (로컬 개발)에만 영향을 줍니다.
> Azure Functions에서는 host가 핸들러를 관리합니다. host가 관리하는 핸들러에 JSON 출력을 설정하려면
> `functions_formatter=JsonFormatter()`를 사용하세요. Azure에서 `format="json"`을 전달하면 경고가 발생합니다.

독립 실행형 로컬 개발 또는 CI 출력의 경우:

```python
setup_logging(format="json")
```

Azure Functions / Core Tools에서는 host가 핸들러를 소유합니다. 기존의 host 관리 핸들러에 JSON 포맷을 강제하려면:

```python
from azure_functions_logging import JsonFormatter, setup_logging

setup_logging(functions_formatter=JsonFormatter())
```

로그 라인당 출력 (NDJSON — 한 줄에 한 JSON 객체):

```json
{"timestamp": "2024-01-15T10:30:00+00:00", "level": "INFO", "logger": "my_module",
 "message": "order accepted", "invocation_id": "abc-123", "function_name": "OrderHandler",
 "cold_start": false, "trace_id": "00-abc...", "exception": null,
 "extra": {"order_id": "o-999"}}
```

추가 필드는 `extra`에 표시되며 Application Insights에서 인덱싱 가능합니다:

```python
logger.info("order accepted", order_id="o-999", tenant_id="t-1")
```

## host.json 충돌 감지

`host.json`이 앱이 발행하는 로그 레벨을 억제하면 시작 시 다음과 같은 경고가 표시됩니다:

```
WARNING: host.json logLevel.default is 'Warning'. Logs below WARNING will be suppressed in Azure.
```

권장 `host.json` 기본값:

```json
{
  "version": "2.0",
  "logging": {
    "logLevel": {
      "default": "Information",
      "Function": "Information"
    }
  }
}
```

### 발견 순서

`host.json`은 현재 작업 디렉토리에서 위로 올라가며 탐색됩니다:

1. `cwd/host.json`
2. 각 상위 디렉토리, 최대 5단계 깊이까지.

먼저 발견된 파일이 사용됩니다. 자동 발견을 우회하려면 (예: 테스트 또는 비표준 레이아웃에서) 명시적 경로를 전달하세요:

```python
from pathlib import Path
from azure_functions_logging import setup_logging

setup_logging(host_json_path=Path("/site/wwwroot/host.json"))
```

## 노이즈 제어

시끄러운 서드파티 로거를 제거하지 않고 억제하세요:

```python
from azure_functions_logging import SamplingFilter, setup_logging
import logging

setup_logging()

# 1초 윈도우당 azure-core 메시지를 최대 10개까지 허용
logging.getLogger("azure").addFilter(SamplingFilter(rate=10))

# 프로덕션에서 urllib3를 완전히 침묵
logging.getLogger("urllib3").setLevel(logging.WARNING)
```

## PII Redaction

민감 필드가 Application Insights에 도달하기 전에 제거하세요:

```python
from azure_functions_logging import RedactionFilter, setup_logging
import logging

setup_logging()
root = logging.getLogger()
root.addFilter(RedactionFilter(sensitive_keys=["password", "token", "secret"]))
```

extra 필드의 키가 sensitive 키와 일치하는 모든 로그 레코드는 해당 값이 `***`로 대체됩니다.

## 로컬 vs 클라우드

| 환경 | 포맷 | 동작 |
|------|------|------|
| 로컬 터미널 | `color` (기본) | 색상 적용된 `[TIME] [LEVEL] [LOGGER] message` |
| Azure / Core Tools | host-managed | 컨텍스트 필터만 설치; host 핸들러에 NDJSON을 강제하려면 `functions_formatter=JsonFormatter()`를 전달 |
| CI / 파이프라인 | `json` | NDJSON, 머신 파싱 가능 |

`setup_logging()`은 `FUNCTIONS_WORKER_RUNTIME`과 `WEBSITE_INSTANCE_ID`를 감지하여 자동으로 올바른 경로를 선택합니다. Azure에서는 핸들러를 추가하지 않고 컨텍스트 필터를 설치합니다 (host 파이프라인의 중복 출력을 피함).

## 컨텍스트 바인딩

요청 범위 메타데이터를 모든 로그에 첨부하되, 모든 호출에 전달하지 않아도 됩니다:

```python
def process_order(order_id: str) -> None:
    order_logger = logger.bind(order_id=order_id, region="eastus")
    order_logger.info("processing started")   # order_id + region 포함
    order_logger.info("processing complete")  # 동일한 메타데이터, 새 메시지
```

호출당 바운드 로거를 생성하세요. 모듈 레벨에서 캐싱하지 마세요.

## 언제 사용하는가

- Application Insights에서 구조화되고 쿼리 가능한 로그가 필요할 때
- 한 요청의 모든 로그에 대해 `invocation_id` 상관관계를 원할 때
- 커스텀 instrumentation 없이 cold start 감지가 필요할 때
- 서드파티 로거에 대해 PII redaction이나 노이즈 제어를 원할 때
- `host.json` 구성이 조용히 로그를 억제하는데 이유를 모를 때

## 문서

- 전체 문서: [yeongseon.github.io/azure-functions-logging-python](https://yeongseon.github.io/azure-functions-logging-python/)
- [Configuration reference](https://yeongseon.github.io/azure-functions-logging-python/configuration/)
- [Troubleshooting guide](https://yeongseon.github.io/azure-functions-logging-python/troubleshooting/)
- [API reference](https://yeongseon.github.io/azure-functions-logging-python/api/)

## 생태계 (Ecosystem)

이 패키지는 **Azure Functions Python DX Toolkit**의 일부입니다.

**디자인 원칙:** `azure-functions-logging`은 구조화된 logging과 호출 인지 관측성을 책임집니다. Python의 표준 `logging`을 보강할 뿐, 대체하지 않습니다. 인접 관심사는 [`azure-functions-openapi`](https://github.com/yeongseon/azure-functions-openapi-python) (API 문서 및 spec 생성), [`azure-functions-validation`](https://github.com/yeongseon/azure-functions-validation-python) (요청/응답 검증 및 직렬화), [`azure-functions-langgraph`](https://github.com/yeongseon/azure-functions-langgraph-python) (LangGraph 런타임 노출)이 담당합니다.

| 패키지 | 역할 |
|--------|------|
| [azure-functions-openapi-python](https://github.com/yeongseon/azure-functions-openapi-python) | OpenAPI spec 생성 및 Swagger UI |
| [azure-functions-validation-python](https://github.com/yeongseon/azure-functions-validation-python) | 요청/응답 검증 및 직렬화 |
| [azure-functions-db-python](https://github.com/yeongseon/azure-functions-db-python) | SQL, PostgreSQL, MySQL, SQLite, Cosmos DB 데이터베이스 바인딩 |
| [azure-functions-langgraph-python](https://github.com/yeongseon/azure-functions-langgraph-python) | Azure Functions용 LangGraph 배포 어댑터 |
| [azure-functions-scaffold-python](https://github.com/yeongseon/azure-functions-scaffold-python) | 프로젝트 스캐폴딩 CLI |
| **azure-functions-logging-python** | 구조화된 logging 및 관측성 |
| [azure-functions-doctor-python](https://github.com/yeongseon/azure-functions-doctor-python) | 사전 배포 진단 CLI |
| [azure-functions-durable-graph-python](https://github.com/yeongseon/azure-functions-durable-graph-python) | Durable Functions 기반 manifest-first 그래프 런타임 *(experimental)* |
| [azure-functions-knowledge-python](https://github.com/yeongseon/azure-functions-knowledge-python) | 지식 검색 (RAG) 데코레이터 |
| [azure-functions-cookbook-python](https://github.com/yeongseon/azure-functions-cookbook-python) | 도그푸딩 예제 — 전체 toolkit을 실행하는 실행 가능한 레시피 |


## AI 코딩 어시스턴트를 위한 안내

이 패키지는 stdlib logging을 수정하지 않고 Azure Functions를 위한 구조화된 logging을 제공합니다.

**LLM 친화적 리소스:**
- `llms.txt` — 간결한 API 레퍼런스와 quick start (저장소 루트)
- `llms-full.txt` — 완전한 API 시그니처, 패턴, 디자인 원칙 (저장소 루트)

**코드 생성을 위한 핵심 구현 세부사항:**

1. **루트 로거를 절대 수정하지 않음** — 핸들러에만 필터/포매터 설치
2. **컨텍스트 주입은 contextvar 기반** — thread-local이 아니므로 asyncio와 호환
3. **멱등성 보장 setup** — `setup_logging()`을 여러 번 호출해도 안전
4. **두 환경, 두 동작**:
   - Azure/Core Tools: 기존 root 핸들러에 필터만 설치 (host.json 존중)
   - 로컬 개발: 지정된 로거에 ColorFormatter 또는 JsonFormatter 핸들러 추가
5. **테스트 친화적**:
   - `inject_context()`는 어떤 객체든 받음 (azure.functions.Context에 강한 의존성 없음)
   - `with_context` 데코레이터는 동기 및 비동기 핸들러에서 동작
   - 필요하다면 테스트 teardown에서 `reset_context()` 사용

**코드 생성 시:**
- `azure_functions_logging` 공개 API에서만 import (밑줄 없음)
- `setup_logging()`은 모듈 레벨이나 핸들러 시작 시 호출 (요청당 호출 X)
- 핸들러에서는 `with logging_context(context):`를 우선 사용; raw `inject_context(context)`는 반드시 `try/finally restore_context(tokens)`와 함께 사용
- 요청당 필드에는 `logger.bind(key=value)` 사용 (logger.extra 직접 X)
- PII 필드에는 `RedactionFilter`, 대량 로그에는 `SamplingFilter` 적용

**예시 패턴:**
```python
from azure_functions_logging import get_logger, logging_context, setup_logging

# 모듈 레벨
setup_logging()
logger = get_logger(__name__)

# 핸들러별
def my_function(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):
        req_logger = logger.bind(correlation_id=req.params.get("id"))
        req_logger.info("Processing")
        return func.HttpResponse("OK")
```


이 프로젝트는 독립적인 커뮤니티 프로젝트이며 Microsoft와 제휴, 후원, 유지보수 관계가 없습니다.

Azure 및 Azure Functions는 Microsoft Corporation의 상표입니다.

## 라이선스

MIT
