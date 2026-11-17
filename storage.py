"""데이터 저장/불러오기 계층.

나중에 외부 저장소(Supabase, Google Sheets 등)로 교체할 수 있도록
load_items / save_items / update_items 만 외부에 노출한다.

- load_items: 파일이 없거나 깨져도, 항목 형식이 틀려도 앱이 죽지 않게 검증/보정해서 반환
- save_items: 임시 파일에 쓴 뒤 교체(원자적 저장)해서 저장 도중 파일이 깨지지 않게 함
- update_items: '최신 데이터 읽기 → 수정 → 저장'을 잠금 안에서 처리
  (여러 탭/세션이 동시에 써도 서로의 변경을 덮어쓰지 않게 함)
"""
import json
import os
import tempfile
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

DATA_PATH = Path(__file__).parent / "data" / "items.json"

MAX_NAME_LENGTH = 100
MAX_QUANTITY = 999

_LOCK = threading.RLock()


def _normalize(raw) -> list[dict]:
    """파일에서 읽은 값을 올바른 항목 리스트로 정리한다. 잘못된 항목은 버린다."""
    if not isinstance(raw, list):
        return []

    result: list[dict] = []
    seen_ids: set[str] = set()
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            continue

        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        name = name.strip()[:MAX_NAME_LENGTH]

        # id 가 없거나 중복이면 위치 기반의 고정 id 를 부여 (재실행해도 값이 바뀌지 않게)
        item_id = entry.get("id")
        if not isinstance(item_id, str) or not item_id or item_id in seen_ids:
            item_id = f"legacy-{index}"
            while item_id in seen_ids:
                item_id += "x"
        seen_ids.add(item_id)

        try:
            quantity = int(entry.get("quantity", 1))
        except (TypeError, ValueError):
            quantity = 1
        quantity = max(1, min(quantity, MAX_QUANTITY))

        checked = entry.get("checked", False)
        if isinstance(checked, str):
            checked = checked.strip().lower() in ("true", "1", "yes", "y")
        else:
            checked = bool(checked)

        created_at = entry.get("created_at")
        if not isinstance(created_at, str):
            created_at = datetime.now().isoformat(timespec="seconds")

        result.append(
            {
                "id": item_id,
                "name": name,
                "quantity": quantity,
                "checked": checked,
                "created_at": created_at,
            }
        )
    return result


def _read_raw() -> list[dict]:
    try:
        # utf-8-sig: BOM 이 붙은 파일도 읽을 수 있다.
        with DATA_PATH.open("r", encoding="utf-8-sig") as f:
            return _normalize(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return []


def _write_raw(items: list[dict]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=DATA_PATH.parent, prefix=".items-", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        os.replace(tmp_name, DATA_PATH)  # 같은 폴더 안에서 원자적으로 교체
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_items() -> list[dict]:
    """저장된 아이템 목록을 불러온다."""
    with _LOCK:
        return _read_raw()


def save_items(items: list[dict]) -> None:
    """아이템 목록 전체를 저장한다."""
    with _LOCK:
        _write_raw(items)


def update_items(
    fn: Callable[[list[dict]], Optional[list[dict]]]
) -> list[dict]:
    """최신 목록을 읽어 fn 으로 수정한 뒤 저장하고, 저장된 목록을 반환한다.

    fn 은 리스트를 직접 수정하거나, 새 리스트를 반환할 수 있다.
    """
    with _LOCK:
        items = _read_raw()
        new_items = fn(items)
        if new_items is not None:
            items = new_items
        _write_raw(items)
        return items
