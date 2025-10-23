import requests
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from urllib.parse import quote_plus

# -------------------------------
# 기본 UI
# -------------------------------
st.set_page_config(page_title="식당 추천 (Kakao)", page_icon="🍽️", layout="wide")
st.title("🍜 식당 추천 (서울) — Kakao Local 버전 ✨")
st.caption("검색: “(구) + (음식명) + 식당”. 지도에서 바로 골라봐! (호버=정보, 클릭=팝업) 😎")

# 메인 페이지에서 고른 음식 기본값
default_food = st.session_state.get("selected_food", "")

SEOUL_GU = [
    "강남구","강동구","강북구","강서구","관악구","광진구","구로구","금천구","노원구","도봉구",
    "동대문구","동작구","마포구","서대문구","서초구","성동구","성북구","송파구","양천구","영등포구",
    "용산구","은평구","종로구","중구","중랑구"
]

EMOJI = {"식당":"🍽️","주소":"📍","전화":"📞","링크":"🔗","카테고리":"🍴","평점":"⭐️"}

# 좌측 컨트롤
c0, c1, c2, c3 = st.columns([1.3, 1, 1, 1.1])
with c0:
    kakao_key = st.text_input("🔑 Kakao REST API Key", type="password", key="kakao_rest_key")
with c1:
    gu = st.selectbox("서울시 **구**", SEOUL_GU, index=SEOUL_GU.index("강남구"), key="gu_select_kakao")
with c2:
    food = st.text_input("**음식명**", value=str(default_food) or "", key="food_input_kakao")
with c3:
    topk = st.slider("개수", 3, 10, 5, key="topk_kakao")

go = st.button("🔎 식당 찾기", key="btn_find_kakao")
st.write("---")

# -------------------------------
# Kakao Local 검색 함수
# -------------------------------
KAKAO_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

def kakao_search_places(rest_key: str, gu: str, food: str, topk: int = 5):
    """
    Kakao Local Keyword Search
    - query: "{구} {food} 식당"
    - category_group_code=FD6 (음식점)
    반환: list[dict(name, address, road_address, phone, url, x, y, category)]
    """
    headers = {"Authorization": f"KakaoAK {rest_key}"}
    q = f"{gu} {food} 식당"
    params = {
        "query": q,
        "category_group_code": "FD6",  # 음식점
        "size": topk,
        "page": 1
    }
    res = requests.get(KAKAO_SEARCH_URL, headers=headers, params=params, timeout=10)
    res.raise_for_status()
    items = res.json().get("documents", [])

    out = []
    for it in items:
        out.append({
            "name": it.get("place_name", ""),
            "address": it.get("address_name", ""),
            "road_address": it.get("road_address_name", ""),
            "phone": it.get("phone", ""),
            "url": it.get("place_url", ""),
            "x": float(it.get("x")) if it.get("x") else None,   # lon
            "y": float(it.get("y")) if it.get("y") else None,   # lat
            "category": it.get("category_name", "")
        })
    return out

def build_html(row: dict) -> str:
    addr = row.get("road_address") or row.get("address") or ""
    phone = row.get("phone") or "번호 정보 없음"
    url = row.get("url") or "#"
    cat = row.get("category") or "-"
    html = f"""
    <div style="font-size:14px; line-height:1.55">
      <div style="font-weight:700">{EMOJI['식당']} {row.get('name','')}</div>
      <div>{EMOJI['카테고리']} {cat}</div>
      <div>{EMOJI['주소']} {addr}</div>
      <div>{EMOJI['전화']} {phone}</div>
      <div>{EMOJI['링크']} <a href="{url}" target="_blank">카카오 상세</a></div>
      <div style="margin-top:6px;color:#666">대표메뉴/가격은 상세 페이지에서 확인하는 게 가장 정확! 🙌</div>
    </div>
    """
    return html

# -------------------------------
# 실행
# -------------------------------
if go:
    if not kakao_key:
        st.warning("카카오 **REST API 키**를 입력해줘! (developers.kakao.com → 내 애플리케이션 → REST API 키)")
        st.stop()
    if not food.strip():
        st.warning("음식명을 입력해줘요! 예: 김치볶음밥, 비빔밥 등 🙂")
        st.stop()

    with st.spinner("카카오한테 물어보고 있어요… 잠깐만! ⏳"):
        try:
            rows = kakao_search_places(kakao_key, gu, food, topk=topk)
        except requests.HTTPError as e:
            st.error(f"요청 오류: {e} — 키가 맞는지/쿼터가 남았는지 확인해줘요.")
            st.stop()
        except Exception as e:
            st.error(f"예상치 못한 오류: {e}")
            st.stop()

    if not rows:
        st.info("결과가 없네요 🥲 검색어를 조금 바꿔보자! 예: 비빔밥 → 전주비빔밥")
        st.stop()

    # 지도 중심 = 첫 결과 좌표
    first = next((r for r in rows if r.get("y") and r.get("x")), None)
    center_lat = first["y"] if first else 37.5665
    center_lon = first["x"] if first else 126.9780

    m = folium.Map(location=[center_lat, center_lon], zoom_start=13, tiles="CartoDB positron")

    for r in rows:
        if not r.get("y") or not r.get("x"):
            continue
        html = build_html(r)
        folium.Marker(
            location=[r["y"], r["x"]],
            tooltip=folium.Tooltip(html, sticky=True),  # 호버 시 정보
            popup=folium.Popup(html, max_width=300),    # 클릭 시 팝업
            icon=folium.Icon(color="red", icon="cutlery", prefix="fa")
        ).add_to(m)

    st.success(f"**{gu}**에서 **{food}** 파는 곳 TOP{topk} 모았어! 지도로 바로 골라보자👇")
    st_folium(m, width=None, height=560)

    # 표로도 제공 (편집/복사 용이)
    df = pd.DataFrame(rows)
    show = df[["name","category","road_address","address","phone","url"]].rename(
        columns={"name":"상호명","category":"분류","road_address":"도로명주소","address":"지번주소","phone":"전화","url":"링크"}
    )
    show.index = range(1, len(show)+1)
    st.dataframe(show, use_container_width=True)

else:
    st.info("왼쪽에서 **REST API 키 + 구 + 음식 + 개수** 고르고 ‘식당 찾기’ 눌러줘! 마커로 쫙~ 찍어줄게 😎")
