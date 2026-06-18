# 新しい予約サイト（プラグイン）を追加する

booking-monitor はサイトごとのスクレイピングを**プラグイン**として扱います。
各プラグインは `BaseSite` を継承したクラスで、設定の `site_type` 文字列から
レジストリ経由で動的に解決されます。新規サイトの追加は次の手順だけで完了します。

## 1. プラグインクラスを作る

`booking_monitor/sites/<your_site>.py` を新規作成し、`BaseSite` を継承して
`check()` を実装します。

```python
from typing import TYPE_CHECKING, Optional, Tuple

from booking_monitor.config import Target
from booking_monitor.sites.base import BaseSite

if TYPE_CHECKING:
    from booking_monitor.sites.browser import BrowserManager


class MySite(BaseSite):
    async def check(
        self, browser_manager: "Optional[BrowserManager]" = None
    ) -> Tuple[bool, str]:
        # (available: bool, summary: str) を返す。
        # ブラウザが必要なら browser_manager を使う（None なら自前で起動）。
        # HTTP だけで十分なら browser_manager は無視してよい。
        ...
```

戻り値の契約は `(available: bool, summary: str)`。致命的エラーは例外を送出します。
サイト構造の変化を区別したい場合は `booking_monitor/sites/exceptions.py` の
`StructureChangeError` を利用できます。

## 2. レジストリに登録する

`booking_monitor/sites/registry.py` の `SITE_REGISTRY` に1行追加します。

```python
SITE_REGISTRY: Dict[str, Type[BaseSite]] = {
    "generic": GenericSite,
    "tablecheck": TableCheckSite,
    "mysite": MySite,   # 追加
}
```

未知の `site_type` は自動的に `GenericSite`（HTTP + キーワード判定）へフォールバック
します。

## 3. 設定で使う

`config.json` の対象に `site_type` を指定します。

```json
{
  "name": "My Restaurant",
  "url": "https://example.com/booking",
  "site_type": "mysite",
  "available_keywords": ["空きあり"],
  "unavailable_keywords": ["満席"]
}
```

`site_type` を省略した場合のデフォルトは `generic` です。

## 4. テストを追加する

`tests/test_site_registry.py` を参考に、解決（`resolve_site` / `get_site_class`）と
プラグインの判定ロジックのテストを追加します。ブラウザ不要のテストは
`pytest -m "not playwright"` で実行できます。
