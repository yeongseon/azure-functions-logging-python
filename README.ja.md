# Azure Functions Logging

> **Azure Functions Python DX Toolkit** の一部 — [azure-functions-cookbook-python](https://github.com/yeongseon/azure-functions-cookbook-python) によりドッグフーディング検証済み。

[![PyPI](https://img.shields.io/pypi/v/azure-functions-logging.svg)](https://pypi.org/project/azure-functions-logging/)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue)](https://pypi.org/project/azure-functions-logging/)
[![CI](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/ci-test.yml/badge.svg)](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/ci-test.yml)
[![Release](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/publish-pypi.yml/badge.svg)](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/publish-pypi.yml)
[![Security Scans](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/security.yml/badge.svg)](https://github.com/yeongseon/azure-functions-logging-python/actions/workflows/security.yml)
[![codecov](https://codecov.io/gh/yeongseon/azure-functions-logging-python/branch/main/graph/badge.svg)](https://codecov.io/gh/yeongseon/azure-functions-logging-python)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://pre-commit.com/)
[![Docs](https://img.shields.io/badge/docs-gh--pages-blue)](https://yeongseon.github.io/azure-functions-logging-python/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

他の言語で読む: [English](README.md) | [한국어](README.ko.md) | [简体中文](README.zh-CN.md)

**Azure Functions Python v2 のための、呼び出し（invocation）認識可能なオブザーバビリティ。**
`invocation_id` を表面化し、コールドスタートを検出し、`host.json` の設定不備を警告し、Application Insights にすぐに使える構造化ログを出力します — Python 標準の `logging` を置き換えることなく。

---

**Azure Functions Python DX Toolkit** の一部
→ FastAPI のような開発体験を Azure Functions にもたらします。

## なぜ存在するのか

Azure Functions Python のロギングには、汎用的なロギングライブラリでは扱えない固有の失敗モードがあります:

| 問題 | 何が起こるか | このライブラリ |
|------|-------------|---------------|
| `host.json` のログレベル衝突 | `INFO` ログが Azure で静かに消える | 起動時に検出して警告 |
| ログに `invocation_id` がない | 特定の実行とログを関連付けられない | `context` オブジェクトから自動注入 |
| コールドスタートが見えない | 新しい worker インスタンス起動時にシグナルなし | 最初の `inject_context()` で自動検出 |
| サードパーティロガーがうるさい | `azure-core`, `urllib3` が Application Insights を埋め尽くす | `SamplingFilter` / `RedactionFilter` |
| ローカルとクラウドの出力不一致 | 色付き出力が本番パイプラインを壊す | 環境認識フォーマッタ自動切替 |
| PII がログに漏洩 | extra フィールド経由で機密値が誤って記録される | キーベースの redaction を行う `RedactionFilter` |

## 何をするのか

- **呼び出しコンテキスト** — すべてのログに `invocation_id`, `function_name`, `cold_start` を自動注入
- **構造化 JSON 出力** — Application Insights にそのまま使える NDJSON フォーマット
- **ノイズ制御** — `SamplingFilter` がうるさいサードパーティロガーをレート制限
- **PII 保護** — `RedactionFilter` が機密フィールドをログ集約に到達する前にマスキング

> **スコープ免責事項。** このパッケージは Python `logging` / stdout に構造化 JSON を書き込みます。これらのフィールドが Application Insights にどう現れるかは、Azure Functions host、worker、ロギング設定、および ingestion パイプラインに依存します。ライブラリは ingestion やスキーマ マッピングを所有しません — `customDimensions` にパースされる形式と、生の `message` 内に残る形式の両方が本番環境で有効です。

## Before / After

`azure-functions-logging` を **使わない場合** — 単純な `print()` 出力、コンテキストなし、構造なし:

```python
import azure.functions as func

app = func.FunctionApp()


@app.route(route="orders")
def process_order(req: func.HttpRequest) -> func.HttpResponse:
    print("Processing order")        # invocation_id なし、構造なし
    print(f"Order: {req.get_json()}")  # PII 漏洩可能、ログレベルなし
    return func.HttpResponse("OK")
```

ターミナル出力:

```
Processing order
Order: {'customer': 'Alice', 'total': 99.99}
```

> Invocation ID なし。ログレベルなし。Application Insights での相関が困難。

`azure-functions-logging` を **使う場合** — 構造化され、クエリ可能、本番環境対応:

```python
import azure.functions as func

from azure_functions_logging import JsonFormatter, get_logger, logging_context, setup_logging

setup_logging(functions_formatter=JsonFormatter())
logger = get_logger(__name__)
app = func.FunctionApp()


@app.route(route="orders")
def process_order(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):
        logger.info("Processing order", order_id="o-999")
        return func.HttpResponse("OK")
```

スタンドアロンで実行した際 (例: `python app.py`、カラーフォーマッタ) のローカルターミナル出力:

```
10:30:00 INFO     function_app  Processing order  [invocation_id=abc-123-def, function_name=process_order, cold_start=true]
```

`func start` / Azure 環境での本番出力 (`functions_formatter` が設定されているため Application Insights 用 NDJSON が適用される):

```json
{"timestamp": "2024-01-15T10:30:00+00:00", "level": "INFO", "logger": "function_app",
 "message": "Processing order", "invocation_id": "abc-123-def",
 "function_name": "process_order", "trace_id": null, "cold_start": true,
 "exception": null, "extra": {"order_id": "o-999"}}
```

> すべてのログに `invocation_id` と `cold_start` が含まれます。Application Insights でクエリ可能。`print()` 文ゼロ。

> **注:** 正確な Application Insights スキーマは ingestion パイプラインに依存します。一部の配置では JSON フィールドが `customDimensions` にパースされ、他の配置では JSON が `message` カラム内に残ります。両方の形式の例を以下に示します。

### Application Insights でのクエリ

#### JSON フィールドが `customDimensions` にパースされる場合

```kql
traces
| where customDimensions.invocation_id == "abc-123-def"
| project timestamp, message, customDimensions.cold_start, customDimensions.function_name
| order by timestamp asc
```

過去 1 時間のすべてのコールドスタートを検索:

```kql
traces
| where customDimensions.cold_start == "true"
| where timestamp > ago(1h)
| summarize count() by bin(timestamp, 5m)
```

#### JSON が `message` カラムに残る場合

```kql
traces
| extend payload = parse_json(message)
| where tostring(payload.invocation_id) == "abc-123-def"
| project timestamp, tostring(payload.message), tostring(payload.cold_start), tostring(payload.function_name)
| order by timestamp asc
```

過去 1 時間のすべてのコールドスタートを検索:

```kql
traces
| extend payload = parse_json(message)
| where tostring(payload.cold_start) == "true"
| where timestamp > ago(1h)
| summarize count() by bin(timestamp, 5m)
```

## このパッケージがしないこと

このパッケージは以下を所有しません:

- **stdlib logging の置き換え** — Python 標準の `logging` をラップして強化するだけで、決して置き換えません
- **分散トレーシング** — エンドツーエンドのトレース相関には OpenTelemetry または Application Insights SDK を使用してください
- **API ドキュメント** — API ドキュメントと spec 生成には [`azure-functions-openapi`](https://github.com/yeongseon/azure-functions-openapi-python) を使用してください

## インストール

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
    with logging_context(context):  # invocation_id, function_name, cold_start をバインドし、終了時に以前のコンテキストへ復元
        logger.info("Request received")
        # ログレコードに invocation_id, function_name, cold_start が付与されます

        return func.HttpResponse("OK")
```

`logging_context` は推奨される主要パターンです。エンター時にコンテキストを注入し、（ハンドラが例外を発生させても）終了時に **常に** 前のコンテキストを復元するため、再利用された worker で古いコンテキストが次の呼び出しに漏れることを防ぎます。

低レベル制御またはカスタムミドルウェアと統合する場合は、トークンベース復元を使用してください:

```python
from azure_functions_logging import inject_context, restore_context

# `logger` と `context` がスコープにあると仮定 (Quick Start を参照)。
tokens = inject_context(context)
try:
    logger.info("Request received")
finally:
    restore_context(tokens)
```

`reset_context()` は意図的にすべてのコンテキストをクリアしたい場合 (例: テストの teardown) のみ使用してください。

ローカルで Functions host を起動 ([e2e サンプルアプリ](examples/e2e_app) 使用):

```bash
func start --script-root examples/e2e_app
```

### ローカルおよび Azure での検証

デプロイ後 ([docs/deployment.md](docs/deployment.md) 参照)、同じリクエストは両環境で同じレスポンスを生成します。

#### ローカル

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

> koreacentral リージョンの一時的な Azure Functions デプロイで検証 (Python 3.12, Consumption plan)。レスポンスをキャプチャし、URL は匿名化されています。

## 呼び出しコンテキスト (Invocation Context)

ハンドラの実行期間中に呼び出しコンテキストをバインドするには `logging_context()` を使用します。以下を設定します:

- `invocation_id` — 実行ごとに一意、1 リクエストのすべてのログを相関させる
- `function_name` — Azure Functions の関数名
- `trace_id` — プラットフォームからのトレースコンテキスト。有効な W3C `traceparent` ヘッダーからのみ抽出され、厳格に検証されるため不正な値は無視されます
- `cold_start` — この worker プロセスの最初の呼び出しで `True`

> **`cold_start` のセマンティクス。** `cold_start=True` は *モジュールロード後にこの Python worker プロセスで観測された最初の呼び出し* を意味します。**プラットフォームレベル** のコールドスタートメトリックではなく、Azure Functions メトリクスが報告する App Service plan / instance 割当のコールドスタートには対応しません。同じ worker での後続の呼び出しは、worker がリサイクルされるまで `cold_start=False` を発行します。

```python
def my_function(req, context):
    with logging_context(context):
        logger.info("handler started")
        # ここから先のすべてのログに invocation_id と cold_start が含まれる
```

低レベル制御 (例: ミドルウェア) には、`inject_context()` と `restore_context()` を使用します:

```python
tokens = inject_context(context)
try:
    logger.info("handler started")
finally:
    restore_context(tokens)
```

コンテキスト注入なしでは、これらのフィールドはすべてのログ行で `None` です。

### `with_context` デコレータ

ボイラープレートを減らすには、`inject_context()` を手動で呼び出す代わりに `with_context` デコレータを使用します:

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

デコレータは名前で `context` パラメータを見つけ、ハンドラ実行前に `inject_context()` を呼び出し、戻った後 `finally` で以前のコンテキストへ復元します。

カスタムパラメータ名:

```python
@with_context(param="ctx")
def hello(req: func.HttpRequest, ctx: func.Context) -> func.HttpResponse:
    ...
```

同期および非同期ハンドラの両方がサポートされます。

### グローバル LogRecordFactory (オプトイン)

`setup_logging()` の後にハンドラが追加される可能性がある、またはハンドラ/フィルタ設定に関係なく **すべての** `LogRecord` に呼び出しコンテキストを乗せたいアプリケーションでは、起動時にグローバルコンテキストファクトリを一度インストールしてください:

```python
from azure_functions_logging import install_context_factory, setup_logging

install_context_factory()  # レコード生成時にコンテキストを注入
setup_logging()
```

有効化されると、`invocation_id`, `function_name`, `trace_id`, `cold_start` は予約された `LogRecord` 属性となります。stdlib `extra=` 経由で渡すと `KeyError` が発生します。キーを自動的にサニタイズする `FunctionLogger` を使用するか、別のキー名を選択してください。

> **`setup_logging()` との関係:** `use_record_factory=False` (デフォルト) の場合、`setup_logging()` はハンドラに `ContextFilter` をインストールします。両方を呼び出しても問題ありません — 同じ値を設定するため衝突しません。`install_context_factory()` は後で追加されたハンドラやフィルタチェーンをバイパスするロガーでもカバレッジを保証します。
>
> `use_record_factory=True` の場合、`setup_logging()` はファクトリモードに切り替えます: 既存のルートハンドラから `ContextFilter` インスタンスを削除してから `LogRecordFactory` を登録します。これにより二重注入を防ぎながら、すべてのレコードにコンテキストが付与されることを保証します。
## 構造化 JSON 出力 (本番)

ログが Application Insights や任意の集約システムに流れる場合は JSON フォーマットを使用してください:

> **注:** `format` パラメータは、このライブラリが作成したハンドラ (ローカル開発) にのみ影響します。
> Azure Functions では host がハンドラを管理します。host が管理するハンドラに JSON 出力を設定するには
> `functions_formatter=JsonFormatter()` を使用してください。Azure で `format="json"` を渡すと警告が発生します。

スタンドアロンのローカル開発または CI 出力の場合:

```python
setup_logging(format="json")
```

Azure Functions / Core Tools では host がハンドラを所有します。既存の host 管理ハンドラに JSON フォーマットを強制するには:

```python
from azure_functions_logging import JsonFormatter, setup_logging

setup_logging(functions_formatter=JsonFormatter())
```

ログ行ごとの出力 (NDJSON — 1 行 1 JSON オブジェクト):

```json
{"timestamp": "2024-01-15T10:30:00+00:00", "level": "INFO", "logger": "my_module",
 "message": "order accepted", "invocation_id": "abc-123", "function_name": "OrderHandler",
 "cold_start": false, "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736", "exception": null,
 "extra": {"order_id": "o-999"}}
```

追加フィールドは出力される JSON の `extra` に含まれます。Application Insights で直接インデックス可能かどうかは ingestion パイプラインに依存します: JSON が `customDimensions` にパースされる場合は直接クエリ可能ですが、JSON が `message` カラムに残る場合はまず `parse_json(message)` を通す必要があります.

```python
logger.info("order accepted", order_id="o-999", tenant_id="t-1")
```

### 長い文字列値の切り詰め (オプトイン)

デフォルトでは `JsonFormatter` は `extra` の文字列値を全長で保持します。
`truncate_native_strings=True` を渡すと `max_string_length` 文字 (デフォルト 2048) でクリップします。
切り詰められた文字列には `…` サフィックスが付加され、切り詰めを検出できます:

```python
from azure_functions_logging import JsonFormatter, setup_logging

setup_logging(functions_formatter=JsonFormatter(
    truncate_native_strings=True,
    max_string_length=512,
))
```

> **スコープ:** `extra` の文字列値のみが切り詰められます (dict と list を再帰的に探索)。
> `message` フィールド、整数、浮動小数点数、ブール値は影響を受けません。

```python
logger.info("order accepted", order_id="o-999", tenant_id="t-1")
```

## host.json 衝突検出

`host.json` がアプリが発行するログレベルを抑制する場合、起動時にこの警告が表示されます:

```
host.json logLevel for default is set to 'Warning' which is more restrictive than the configured level 'INFO'. Logs below 'Warning' will be suppressed by the Azure Functions host.
```

推奨される `host.json` ベースライン:

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

### 探索順序

`host.json` は現在の作業ディレクトリ (または `AzureWebJobsScriptRoot` 環境変数が設定されている場合はそのディレクトリ) から上に向かって探索されます:

| 優先度 | ソース |
|--------|--------|
| 1 | `setup_logging()` に渡した明示的な `host_json_path` パラメータ |
| 2 | `AzureWebJobsScriptRoot` 環境変数 |
| 3 | `cwd/host.json` および各親ディレクトリ、最大 5 階層 |

最初に存在する `host.json` が採用されます。`AzureWebJobsScriptRoot` はAzure Functions ホストが設定する公式の環境変数で、ディレクトリ自体のみを探索します (祖先ウォークなし)。

最初に存在するファイルが採用されます。自動探索をバイパスするには (テストや非標準レイアウトなど)、明示的なパスを渡してください:

```python
from pathlib import Path
from azure_functions_logging import setup_logging

setup_logging(host_json_path=Path("/site/wwwroot/host.json"))
```

## ノイズ制御

うるさいサードパーティロガーを削除せずに抑制します:

```python
from azure_functions_logging import SamplingFilter, setup_logging
import logging

setup_logging()

# ノイズーな azure.* ロガーをサンプリング: 1 秒ウィンドウあたり最大 10 レコードを保持
# ロガーにアタッチしたフィルターは、子ロガーから伝播されるレコードには実行されないため、
# ルートハンドラーにアタッチし、ロガー名でスコープを限定します。
for handler in logging.getLogger().handlers:
    handler.addFilter(SamplingFilter(rate=10, name="azure"))

# 本番で urllib3 を完全に沈黙
logging.getLogger("urllib3").setLevel(logging.WARNING)
```

## PII Redaction

機密フィールドが Application Insights に到達する前に削除します:

```python
from azure_functions_logging import RedactionFilter, setup_logging
import logging

setup_logging()
root = logging.getLogger()
# 名前付きの子ロガーから出力されるレコードもリダクトされるよう、フィルタはハンドラに付与します。
for handler in root.handlers:
    handler.addFilter(RedactionFilter(sensitive_keys=["password", "token", "secret"]))
```

extra フィールドのキーが sensitive キーと一致するすべてのログレコードは、その値が `***` で置き換えられます。

## ローカル vs クラウド

| 環境 | フォーマット | 動作 |
|------|------------|------|
| ローカルターミナル | `color` (デフォルト) | 色付きで人間が読める形式: `HH:MM:SS LEVEL logger  message [context...]` |
| Azure / Core Tools | host-managed | コンテキストフィルタのみインストール; host ハンドラに NDJSON を強制するには `functions_formatter=JsonFormatter()` を渡す |
| CI / パイプライン | `json` | NDJSON、機械パース可能 |

`setup_logging()` は `FUNCTIONS_WORKER_RUNTIME` を検出し、Azure Functions / Core Tools とスタンドアロンのローカル実行を区別します。Azure モードではハンドラを追加せずにコンテキストフィルタをインストールします (host パイプラインからの重複出力を回避)。

## コンテキストバインディング

リクエストスコープのメタデータを各呼び出しに渡すことなく、すべてのログにアタッチします:

```python
def process_order(order_id: str) -> None:
    order_logger = logger.bind(order_id=order_id, region="eastus")
    order_logger.info("processing started")   # order_id + region を含む
    order_logger.info("processing complete")  # 同じメタデータ、新しいメッセージ
```

呼び出しごとにバインドされたロガーを作成してください。モジュールレベルでキャッシュしないでください。

## いつ使うか

- Application Insights で構造化されクエリ可能なログが必要なとき
- 単一リクエストのすべてのログにわたる `invocation_id` 相関が必要なとき
- カスタム instrumentation なしでコールドスタート検出が必要なとき
- サードパーティロガーに対して PII redaction やノイズ制御が必要なとき
- `host.json` 設定が静かにログを抑制し、その理由がわからないとき

## ドキュメント

- 完全なドキュメント: [yeongseon.github.io/azure-functions-logging-python](https://yeongseon.github.io/azure-functions-logging-python/)
- [Configuration reference](https://yeongseon.github.io/azure-functions-logging-python/configuration/)
- [Troubleshooting guide](https://yeongseon.github.io/azure-functions-logging-python/troubleshooting/)
- [API reference](https://yeongseon.github.io/azure-functions-logging-python/api/)

## エコシステム

このパッケージは **Azure Functions Python DX Toolkit** の一部です。

**設計原則:** `azure-functions-logging` は構造化ロギングと呼び出し認識オブザーバビリティを所有します。Python 標準の `logging` を強化します — 置き換えません。隣接する関心事は [`azure-functions-openapi`](https://github.com/yeongseon/azure-functions-openapi-python) (API ドキュメントと spec 生成)、[`azure-functions-validation`](https://github.com/yeongseon/azure-functions-validation-python) (リクエスト/レスポンス検証とシリアライゼーション)、[`azure-functions-langgraph`](https://github.com/yeongseon/azure-functions-langgraph-python) (LangGraph ランタイム公開) に属します。

| パッケージ | 役割 |
|----------|------|
| [azure-functions-openapi-python](https://github.com/yeongseon/azure-functions-openapi-python) | OpenAPI spec 生成と Swagger UI |
| [azure-functions-validation-python](https://github.com/yeongseon/azure-functions-validation-python) | リクエスト/レスポンス検証とシリアライゼーション |
| [azure-functions-db-python](https://github.com/yeongseon/azure-functions-db-python) | SQL, PostgreSQL, MySQL, SQLite, Cosmos DB のデータベースバインディング |
| [azure-functions-langgraph-python](https://github.com/yeongseon/azure-functions-langgraph-python) | Azure Functions 向け LangGraph デプロイアダプタ |
| [azure-functions-scaffold-python](https://github.com/yeongseon/azure-functions-scaffold-python) | プロジェクトスキャフォールディング CLI |
| **azure-functions-logging-python** | 構造化ロギングとオブザーバビリティ |
| [azure-functions-doctor-python](https://github.com/yeongseon/azure-functions-doctor-python) | デプロイ前診断 CLI |
| [azure-functions-durable-graph-python](https://github.com/yeongseon/azure-functions-durable-graph-python) | Durable Functions ベースのマニフェストファーストグラフランタイム *(experimental)* |
| [azure-functions-knowledge-python](https://github.com/yeongseon/azure-functions-knowledge-python) | 知識検索 (RAG) デコレータ |
| [azure-functions-cookbook-python](https://github.com/yeongseon/azure-functions-cookbook-python) | ドッグフード例 — toolkit 全体を実行する実行可能なレシピ |


## AI コーディングアシスタント向け

このパッケージは stdlib logging に変更を加えずに Azure Functions に構造化ロギングを提供します。

**LLM フレンドリーなリソース:**
- `llms.txt` — 簡潔な API リファレンスと quick start (リポジトリルート)
- `llms-full.txt` — 完全な API シグネチャ、パターン、設計原則 (リポジトリルート)

**コード生成のための主要な実装詳細:**

1. **ホスト構成を尊重** — Azure / Core Tools ではハンドラを追加せず、ルートロガーのレベルは `host.json` に委ねます。既存のルートハンドラとルートロガー自身に `ContextFilter` をインストールします（ルートロガーでの直接呼び出しはコンテキストを仲介する）。名前付きの子ロガーから伝搬されて後から追加されたハンドラへ到達するレコードにもコンテキストを保証したい場合は `install_context_factory()` を呼び出してください。ローカル単独モードでは `setup_logging(logger_name=None)` がルートロガーを構成します（レベル設定、ハンドラがなければ `StreamHandler` 追加）。
2. **コンテキスト注入は contextvar ベース** — thread-local ではなく、asyncio で動作
3. **冪等な setup** — `setup_logging()` を複数回呼び出しても安全
4. **2 つの環境、2 つの動作**:
   - Azure/Core Tools: 既存の root ハンドラと root ロガー自身に `ContextFilter` をインストールします。ハンドラの追加や root レベルの変更は行いません (`host.json` を尊重)。
   - スタンドアロンのローカル実行: 対象/ルートロガーのレベルを設定します。**ハンドラが 1 つも存在しない場合に限り** `StreamHandler` (ColorFormatter または JsonFormatter) を追加し、そうでなければ既存のハンドラにフィルタのみ付加します。
5. **テストフレンドリー**:
   - `inject_context()` は任意のオブジェクトを受け入れる (azure.functions.Context への強い依存なし)
   - `with_context` デコレータは同期および非同期ハンドラで動作
   - 必要に応じてテスト teardown で `reset_context()` を使用

**コード生成時:**
- `azure_functions_logging` の公開 API からのみインポート (アンダースコアなし)
- `setup_logging()` をモジュールレベルまたはハンドラ起動時に呼び出す (リクエストごとではない)
- ハンドラでは `with logging_context(context):` を優先; 生の `inject_context(context)` は `try/finally restore_context(tokens)` とのみ併用
- リクエストごとのフィールドには `logger.bind(key=value)` を使用 (logger.extra への直接アクセスではない)
- 暗黙的なハンドラごとのコンテキスト注入を好む場合は `with_context` デコレータを使用
- 関数の `@with_context` メタデータを検査するには `get_logging_metadata(func)` を呼び出す (`dict[str, Any] | None` を返却)
- PII フィールドには `RedactionFilter`、大量ログには `SamplingFilter` を適用

**例パターン:**
```python
from azure_functions_logging import get_logger, logging_context, setup_logging

# モジュールレベル
setup_logging()
logger = get_logger(__name__)

# ハンドラごと
def my_function(req: func.HttpRequest, context: func.Context) -> func.HttpResponse:
    with logging_context(context):
        req_logger = logger.bind(correlation_id=req.params.get("id"))
        req_logger.info("Processing")
        return func.HttpResponse("OK")
```


このプロジェクトは独立したコミュニティプロジェクトであり、Microsoft と提携、承認、保守関係にはありません。

Azure および Azure Functions は Microsoft Corporation の商標です。

## ライセンス

MIT
