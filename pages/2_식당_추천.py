import requests
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import re
from urllib.parse import quote_plus

# -------------------------------
# 기본 UI
# -------------------------------
st.set_page_config(page_title="식당 추천 (키 없이 모드 지원)", page_icon="🍽️", layout="wide")
st.title("🍜 식당 추천 (서울) — Kakao / 키 없이(Beta) ✨")
st.caption("검색: “(구) + (음식명) + 식당”. 지도에서 바로 골라봐! (호버=정보, 클릭=팝업) 😎")

default_food = st.session_state.get("selected_food", "")

SEOUL_GU = [
    "강남구","강동구","강북구","강서구","관악구","광진구","구로구","금천구","노원구","도봉구",
    "동대문구","동작구","마포구","서대문구","서초구","성동구","성북구","송파구","양천구","영등포구",
    "용산구","은평구","종로구","중구","중랑구"
]
EMOJI = {"식당":"🍽️","주소":"📍","전화":"📞","링크":"🔗","카테고리":"🍴"}

c0, c1, c2, c3 = st.columns([1.6, 1, 1, 1.1])
with c0:
    kakao_key = st.text_input("🔑 Kakao REST API Key (없으면 비워두세요)", type="password", key="kakao_rest_key")
with c1:
    gu = st.selectbox("서울시 **구**", SEOUL_GU, index=SEOUL_GU.index("강남구"), key="gu_select_all")
with c2:
    food = st.text_input("**음식명**", value=str(default_food) or "", key="food_input_all")
with c3:
    topk = st.slider("개수", 3, 10, 5, key="topk_all")

use_keyless = st.toggle("🔓 API 키 없이 빠르게(Beta)", value=(not bool(kakao_key)), help="체크하면 오픈스트리트맵(Overpass)을 사용해 키 없이 검색합니다.")
go = st.button("🔎 식당 찾기", key="btn_find_all")
st.write("---")

# -------------------------------
# Kakao Local 검색 (있으면 사용)
# -------------------------------
KAKAO_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

def kakao_search_places(rest_key: str, gu: str, food: str, topk: int = 5):
    headers = {"Authorization": f"KakaoAK {rest_key}"}
    q = f"{gu} {food} 식당"
    params = {"query": q, "category_group_code": "FD6", "size": topk, "page": 1}
    res = requests.get(KAKAO_URL, headers=headers, params=params, timeout=10)
    res.raise_for_status()
    docs = res.json().get("documents", [])
    out = []
    for d in docs:
        out.append({
            "name": d.get("place_name",""),
            "category": d.get("category_name",""),
            "road_address": d.get("road_address_name",""),
            "address": d.get("address_name",""),
            "phone": d.get("phone",""),
            "url": d.get("place_url",""),
            "lat": float(d["y"]) if d.get("y") else None,
            "lon": float(d["x"]) if d.get("x") else None
        })
    return out

# -------------------------------
# Overpass(키 없이) 검색
#  - 구 경계(area) 안에서 amenity=restaurant
#  - name / name:ko / cuisine 태그에 음식 키워드가 포함된 곳만
# -------------------------------
OVERPASS = "https://overpass-api.de/api/interpreter"

def overpass_restaurants(gu: str, food: str, topk: int = 5):
    # Overpass 쿼리: 행정구역(구) 영역 찾은 뒤 레스토랑 탐색
    # admin_level=6: 구/군
    food_esc = re.sub(r'(["\\])', r"\\\1", food)  # 따옴표/역슬래시 이스케이프
    query = f"""
    [out:json][timeout:25];
    area["name:ko"="{gu}"]["boundary"="administrative"]["admin_level"="6"]->.a;
    (
      node["amenity"="restaurant"]["name:ko"~"{food_esc}", i](area.a);
      node["amenity"="restaurant"]["name"~"{food_esc}", i](area.a);
      node["amenity"="restaurant"]["cuisine"~"{food_esc}", i](area.a);
      way["amenity"="restaurant"]["name:ko"~"{food_esc}", i](area.a);
      way["amenity"="restaurant"]["name"~"{food_esc}", i](area.a);
      way["amenity"="restaurant"]["cuisine"~"{food_esc}", i](area.a);
    );
    out center {topk};
    """
    res = requests.post(OVERPASS, data={"data": query}, timeout=30)
    res.raise_for_status()
    data = res.json()
    elements = data.get("elements", [])
    out = []
    for el in elements[:topk]:
        tags = el.get("tags", {})
        name = tags.get("name:ko") or tags.get("name") or ""
        cat = tags.get("cuisine") or ""
        addr = tags.get("addr:full") or " ".join(
            filter(None, [tags.get("addr:city"), tags.get("addr:district"), tags.get("addr:neighbourhood"),
                          tags.get("addr:street"), tags.get("addr:housenumber")])
        )
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        url = f"https://map.naver.com/p/search/{quote_plus(name)}" if name else ""
        out.append({
            "name": name, "category": cat, "road_address": addr, "address": addr,
            "phone": "", "url": url, "lat": lat, "lon": lon
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
      <div>{EMOJI['링크']} <a href="{url}" target="_blank">자세히 보기</a></div>
      <div style="margin-top:6px;color:#666">대표메뉴/가격은 링크에서 확인하는 게 가장 정확! 🙌</div>
    </div>
    """
    return html

# -------------------------------
# 실행
# -------------------------------
if go:
    if not food.strip():
        st.warning("음식명을 입력해줘요! 예: 김치볶음밥, 비빔밥 등 🙂")
        st.stop()

    if kakao_key and not use_keyless:
        # Kakao 모드
        with st.spinner("카카오에서 찐 식당만 가져오는 중… ⏳"):
            try:
                rows = kakao_search_places(kakao_key, gu, food, topk)
            except requests.HTTPError as e:
                st.error(f"요청 오류: {e} — 키/쿼터 확인해줘요.")
                st.stop()
    else:
        # 키 없이 모드 (Overpass)
        with st.spinner("키 없이 찾는 중… 데이터가 조금 제한적일 수 있어요! ⏳"):
            try:
                rows = overpass_restaurants(gu, food, topk)
            except Exception as e:
                st.error(f"검색 실패: {e}")
                st.stop()

    if not rows:
        st.info("결과가 없네요 🥲  키워드를 바꿔보거나(예: 비빔밥→전주비빔밥), 키 사용 모드로 전환해보세요.")
        st.stop()

    # 지도 중심
    first = next((r for r in rows if r.get("lat") and r.get("lon")), None)
    center_lat = first["lat"] if first else 37.5665
    center_lon = first["lon"] if first else 126.9780

    m = folium.Map(location=[center_lat, center_lon], zoom_start=13, tiles="CartoDB positron")

    for r in rows:
        if not r.get("lat") or not r.get("lon"):
            continue
        html = build_html(r)
        folium.Marker(
            location=[r["lat"], r["lon"]],
            tooltip=folium.Tooltip(html, sticky=True),
            popup=folium.Popup(html, max_width=300),
            icon=folium.Icon(color="red", icon="cutlery", prefix="fa")
        ).add_to(m)

    mode_txt = "키 없이(Beta)" if (use_keyless or not kakao_key) else "Kakao"
    st.success(f"**{gu}**에서 **{food}** 파는 곳 TOP{len(rows)} — {mode_txt} 모드로 가져왔어! 🙌")
    st_folium(m, width=None, height=560)

    df = pd.DataFrame(rows)
    show = df[["name","category","road_address","address","phone","url"]].rename(
        columns={"name":"상호명","category":"분류","road_address":"도로명주소","address":"지번/전체주소","phone":"전화","url":"링크"}
    )
    show.index = range(1, len(show)+1)
    st.dataframe(show, use_container_width=True)

else:
    st.info("왼쪽에서 **구 + 음식 + 개수** 고르고 ‘식당 찾기’ 눌러줘!  키가 없으면 “키 없이(Beta)”로 바로 보여줄게 😎")
