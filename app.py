import re
import uuid
from datetime import datetime

import streamlit as st

from storage import MAX_NAME_LENGTH, MAX_QUANTITY, load_items, update_items

FILTERS = ["전체", "미완료", "완료"]

st.set_page_config(page_title="쇼핑리스트", page_icon="🛒", layout="centered")

# ---------- 상태 ----------
# 목록 자체는 세션에 보관하지 않는다. 매 실행/동작마다 저장소에서 최신 상태를 읽어
# 여러 탭에서 동시에 사용해도 서로의 변경을 덮어쓰지 않게 한다.
st.session_state.setdefault("editing_id", None)  # 수정 중인 아이템 id (한 번에 하나)


ZERO_WIDTH = "​"  # 화면에 보이지 않는 문자 (저장 데이터에는 넣지 않고 표시용 라벨에만 사용)


def escape_md(text: str) -> str:
    """사용자 입력이 마크다운(링크/색상 문법 등)으로 해석되지 않도록 만든 표시용 문자열.

    1) 마크다운 특수문자를 백슬래시로 이스케이프한다.
    2) URL/이메일 자동 링크는 백슬래시로 막을 수 없으므로, 자동 링크가 만들어지는 지점
       (':' '@' 와 'www' 바로 뒤)에 폭 0 문자를 넣어 끊는다.
    """
    text = re.sub(r"([\\`*_{}\[\]()#+\-.!~|>$<&:@])", r"\\\1", text)
    text = re.sub(r"([:@])", r"\1" + ZERO_WIDTH, text)
    return re.sub(r"(?i)(www)", r"\1" + ZERO_WIDTH, text)


def clamp_quantity(value) -> tuple[int, bool]:
    """수량을 1~MAX_QUANTITY 로 맞추고, 상한에 걸려 줄였는지 함께 반환한다."""
    qty = int(value)
    if qty > MAX_QUANTITY:
        return MAX_QUANTITY, True
    return max(1, qty), False


def flash(kind: str, message: str) -> None:
    """다음 화면 갱신 때 한 번 보여줄 안내 메시지를 예약한다."""
    st.session_state["flash"] = (kind, message)


# ---------- 동작(콜백) ----------
def add_item(name: str, quantity: int) -> None:
    new_item = {
        "id": uuid.uuid4().hex,
        "name": name,
        "quantity": quantity,
        "checked": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    update_items(lambda items: items.append(new_item))


def toggle_item(item_id: str) -> None:
    checked = bool(st.session_state.get(f"check_{item_id}"))

    def apply(items: list[dict]) -> None:
        for item in items:
            if item["id"] == item_id:
                item["checked"] = checked
                break

    update_items(apply)


def delete_item(item_id: str) -> None:
    update_items(lambda items: [i for i in items if i["id"] != item_id])
    if st.session_state["editing_id"] == item_id:
        st.session_state["editing_id"] = None


def start_edit(item_id: str) -> None:
    st.session_state["editing_id"] = item_id


def cancel_edit() -> None:
    st.session_state["editing_id"] = None


def update_item(item_id: str, name: str, quantity: int) -> None:
    def apply(items: list[dict]) -> None:
        for item in items:
            if item["id"] == item_id:
                item["name"] = name
                item["quantity"] = quantity
                break

    update_items(apply)
    st.session_state["editing_id"] = None


def clear_checked() -> None:
    update_items(lambda items: [i for i in items if not i["checked"]])
    st.session_state["editing_id"] = None


def reset_all() -> None:
    update_items(lambda items: [])
    st.session_state["editing_id"] = None
    st.session_state["confirm_reset"] = False


# ---------- 스타일 ----------
# 최소한의 CSS: 레이아웃 폭, 한 줄 배치 유지(모바일), 완료 구분 영역
st.markdown(
    """
    <style>
    .block-container { padding-top: 2.5rem; padding-bottom: 3rem; max-width: 640px; }
    /* 모바일에서도 한 줄 배치가 줄바꿈되지 않도록 고정 */
    .st-key-addbar [data-testid="stHorizontalBlock"],
    [class*="st-key-row_"] [data-testid="stHorizontalBlock"],
    [class*="st-key-editrow_"] [data-testid="stHorizontalBlock"] {
        flex-wrap: nowrap !important; gap: 0.4rem !important;
    }
    .st-key-addbar [data-testid="stColumn"],
    [class*="st-key-row_"] [data-testid="stColumn"],
    [class*="st-key-editrow_"] [data-testid="stColumn"] { min-width: 0 !important; }
    /* 아이템 행: 아이콘 버튼 열은 내용 폭만 차지 */
    [class*="st-key-row_"] [data-testid="stColumn"]:not(:first-child) {
        flex: 0 0 auto !important; width: auto !important;
    }
    [class*="st-key-row_"] { padding: 0.15rem 0.25rem; }
    .section-label { font-size: 0.85rem; opacity: 0.65; margin: 1.1rem 0 0.3rem; }
    .empty-box { text-align: center; padding: 2.5rem 0; opacity: 0.75; }
    .empty-box .emoji { font-size: 2.6rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------- 화면 ----------
# 이 시점의 최신 목록 (위의 콜백들은 이 줄보다 먼저 실행된다)
all_items = load_items()
ids = {i["id"] for i in all_items}
if st.session_state["editing_id"] not in ids:
    st.session_state["editing_id"] = None  # 다른 탭에서 삭제된 항목은 수정 모드 해제

st.title("🛒 쇼핑리스트")

total = len(all_items)
done = sum(1 for i in all_items if i["checked"])
st.progress(done / total if total else 0.0, text=f"{done} / {total} 완료")

# 예약된 안내 메시지 (한 번만 표시)
if "flash" in st.session_state:
    kind, message = st.session_state.pop("flash")
    getattr(st, kind)(message)

# 아이템 추가 폼
with st.container(key="addbar"):
    with st.form("add_form", clear_on_submit=True, border=False):
        col_name, col_qty, col_btn = st.columns([5, 2, 2], vertical_alignment="bottom")
        name_input = col_name.text_input(
            "아이템 이름", max_chars=MAX_NAME_LENGTH, placeholder="무엇을 살까요?",
            label_visibility="collapsed",
        )
        # max_value 를 두지 않고 코드에서 상한을 처리한다.
        # (위젯의 max_value 를 넘기면 값이 조용히 1로 바뀌어 사용자가 알 수 없기 때문)
        qty_input = col_qty.number_input(
            "수량", min_value=1, value=1, step=1, label_visibility="collapsed",
        )
        submitted = col_btn.form_submit_button(
            "추가", type="primary", use_container_width=True
        )

if submitted:
    name = name_input.strip()
    if not name:
        st.warning("아이템 이름을 입력해주세요.")
    else:
        qty, clamped = clamp_quantity(qty_input)
        add_item(name, qty)
        if clamped:
            flash("info", f"수량은 최대 {MAX_QUANTITY}개까지라 {MAX_QUANTITY}개로 저장했어요.")
        st.rerun()

# 필터
filter_mode = st.radio(
    "보기", FILTERS, horizontal=True, key="filter_mode", label_visibility="collapsed"
)

if filter_mode == "미완료":
    visible = [i for i in all_items if not i["checked"]]
elif filter_mode == "완료":
    visible = [i for i in all_items if i["checked"]]
else:
    visible = all_items

# 화면 표시 순서만 바꾼다: 미완료 먼저, 완료는 아래 구분 영역 (저장 순서는 그대로)
pending = [i for i in visible if not i["checked"]]
completed = [i for i in visible if i["checked"]]


def render_item(item: dict) -> None:
    item_id = item["id"]
    if st.session_state["editing_id"] == item_id:
        # 수정 모드
        with st.container(border=True, key=f"editrow_{item_id}"):
            with st.form(f"edit_form_{item_id}", border=False):
                c1, c2 = st.columns([3, 1])
                new_name = c1.text_input(
                    "이름", value=item["name"], max_chars=MAX_NAME_LENGTH,
                    key=f"edit_name_{item_id}",
                )
                new_qty = c2.number_input(
                    "수량", min_value=1, value=int(item["quantity"]), step=1,
                    key=f"edit_qty_{item_id}",
                )
                b1, b2 = st.columns(2)
                save_clicked = b1.form_submit_button(
                    "저장", type="primary", use_container_width=True
                )
                cancel_clicked = b2.form_submit_button("취소", use_container_width=True)
        if save_clicked:
            if not new_name.strip():
                st.error("아이템 이름을 입력해주세요.")
            else:
                qty, clamped = clamp_quantity(new_qty)
                update_item(item_id, new_name.strip(), qty)
                if clamped:
                    flash(
                        "info",
                        f"수량은 최대 {MAX_QUANTITY}개까지라 {MAX_QUANTITY}개로 저장했어요.",
                    )
                st.rerun()
        elif cancel_clicked:
            cancel_edit()
            st.rerun()
        return

    # 일반 모드
    # 다른 탭에서 바뀐 체크 상태가 위젯의 이전 값에 가려지지 않도록 저장된 값으로 맞춘다.
    st.session_state[f"check_{item_id}"] = item["checked"]
    with st.container(border=True, key=f"row_{item_id}"):
        c_check, c_edit, c_del = st.columns([1, 0.1, 0.1], vertical_alignment="center")
        label = f"{escape_md(item['name'])}  ×{item['quantity']}"
        if item["checked"]:
            label = f":gray[~~{label}~~]"
        c_check.checkbox(
            label,
            key=f"check_{item_id}",
            on_change=toggle_item,
            args=(item_id,),
        )
        c_edit.button(
            "✏️", key=f"edit_{item_id}", help="수정", type="tertiary",
            on_click=start_edit, args=(item_id,),
        )
        c_del.button(
            "🗑️", key=f"del_{item_id}", help="삭제", type="tertiary",
            on_click=delete_item, args=(item_id,),
        )


# 목록
if not all_items:
    st.markdown(
        '<div class="empty-box"><div class="emoji">🧺</div>'
        "아직 항목이 없어요.<br>위에서 사야 할 물건을 추가해보세요.</div>",
        unsafe_allow_html=True,
    )
elif not visible:
    st.markdown(
        f'<div class="empty-box"><div class="emoji">🔍</div>'
        f"'{filter_mode}' 항목이 없어요.</div>",
        unsafe_allow_html=True,
    )

for item in pending:
    render_item(item)

if completed:
    st.markdown(
        f'<div class="section-label">✅ 완료 {len(completed)}</div>',
        unsafe_allow_html=True,
    )
    for item in completed:
        render_item(item)

# 하단 도구
st.divider()
st.button(
    "완료 항목 모두 삭제", on_click=clear_checked, disabled=done == 0,
    use_container_width=True,
)

with st.expander("⚠️ 전체 초기화"):
    confirmed = st.checkbox("정말 모든 항목을 삭제할게요", key="confirm_reset")
    st.button(
        "전체 삭제", on_click=reset_all, disabled=not confirmed or total == 0,
        key="reset_all_btn",
    )
