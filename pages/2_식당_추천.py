import re
import time
import requests
import pandas as pd
import streamlit as st
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from typing import List, Dict, Tuple, Optional

import folium
from streamlit_folium import st_folium

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

st.set_page_config(page_title="식당 추천", page_icon="🍽️", layout="wide")
st.title("🍜 식당 추천 (서울) — 실시간 네이버 픽 ✨")
st.caption("검색: “(구) + (음식명) + 식당”. 지도에서 바로 확인! (호버=정보, 클릭=팝업)")

# -------------------------------
# 상수/유틸
# -------------------------------
SEOUL_GU = [
    "강남구","강동구","강북구","강서구","관악구","광진구","구로구","금천구","노원구","도봉구",
    "동대문구","동작구","마포구","서대문구","서초구","성동구","성북구","송파구","양천구","영등포구",
    "용산구","은평구","종로구","중구","중랑구"
]
EMOJI = {"식당":"🍽️","주소":"📍","전화":"📞","평점":"⭐️","링크":"🔗"}

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/130.0.0.0 Safari/537.36")
}

def strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()

# -------------------------------
# 좌측 컨트롤
# -------------------------------
default_food = st.session_state.get("selected_food", "")
c1, c2, c3 = st.columns([1,1,1.2])
with c1:
    gu = st.selectbox("서울시 **구**", SEOUL_GU, index=SEOUL_GU.index("강남구"), key="gu_select")
with c2:
    food = st.text_input("**음식명**", value=str(default_food) or "", key="food_input_rest")
with c3:
    topk = st.slider("개수", 3, 10, 5, key="topk_slider")

with st.expander("🔑 (선택) NAVER Local API 자격증명 입력 — 정확도↑"):
    cid = st.text_input("Client ID", key="naver_cid")
    csec = st.text_input("Client Secret", type="password", key="naver_csec")
    st.caption("※ developers.naver.com에서 애플리케이션 생성 → 검색(Local) 활성화")

go = st.button("🔎 식당 찾기", key="btn_find_places")
st.write("---")

# -------------------------------
# 데이터 수집: ① 공식 API ② 베스트에포트 스크랩
# -------------------------------
def search_naver_local_api(gu: str, food: str, topk: int,
                           cid: str, csec: str) -> List[Dict]:
    """Naver Local Search API (권장). 반환: dict(name,address,phone,rating,url)"""
    q = f"{gu} {food} 식당"
    url = "https://openapi.naver.com/v1/search/local.json"
    params = {"query": q, "display": topk, "start": 1, "sort": "comment"}
    headers = {"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec}
    res = requests.get(url, headers=headers, params=params, timeout=10)
    res.raise_for_status()
    items = res.json().get("items", [])
    out = []
    for it in items:
        out.append({
            "name": strip_html(it.get("title")),
            "address": it.get("address") or it.get("roadAddress") or "",
            "phone": it.get("telephone") or "",
            "rating": "",  # API 기본 응답엔 평점이 없음
            "url": it.get("link") or it.get("mapx") or ""
        })
    return out

def search_naver_scrape(gu: str, food: str, topk: int) -> List[Dict]:
    """네이버 로컬 검색 결과 페이지에서 가벼운 파싱."""
    q = f"{gu} {food} 식당"
    url = f"https://search.naver.com/search.naver?where=local&query={quote_plus(q)}"
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    results = []
    # 이름: 블루링크/상호 anchor
    for card in soup.select("a.place_bluelink, a.EKPkN"):  # 클래스타입은 수시로 바뀜 → 두 가지 시도
        name = strip_html(card.get_text())
        href = card.get("href", "")
        if not name or not href:
            continue

        # 카드 주변에서 주소/전화/평점 후보 긁기 (유연한 근처 탐색)
        wrap = card.find_parent()
        wrap_text = wrap.get_text(" ", strip=True) if wrap else ""

        # 주소 후보
        addr = ""
        addr_tag = None
        # 근처 span에 주소가 있을 때가 많음
        for sp in (wrap or soup).select("span"):
            txt = sp.get_text(" ", strip=True)
            if txt and any(k in txt for k in ["서울", "구", "로", "길"]) and len(txt) >= 6:
                addr = txt
                addr_tag = sp
                break

        # 평점 후보
        rating = ""
        m = re.search(r"([0-9]\.?[0-9])\s*/\s*5", wrap_text)
        if m:
            rating = m.group(1) + "/5"

        # 전화 후보
        phone = ""
        m2 = re.search(r"0\d{1,2}-\d{3,4}-\d{4}", wrap_text)
        if m2:
            phone = m2.group(0)

        results.append({
            "name": name, "address": addr or f"서울 {gu} {name}",
            "phone": phone, "rating": rating, "url": href
        })
        if len(results) >= topk:
            break

    # 최악의 경우 아무것도 못 잡았으면 지도 검색 링크라도 반환
    if not results:
        results.append({
            "name": "네이버 지도 검색",
            "address": f"{gu} {food} 식당 : 네이버 검색",
            "phone": "", "rating": "", 
            "url": f"https://map.naver.com/p/search/{quote_plus(q)}"
        })
    return results

# -------------------------------
# 지오코딩 (좌표 얻기)
# -------------------------------
@st.cache_data(show_spinner=False)
def geocode_many(rows: List[Dict]) -> List[Tuple[Optional[float], Optional[float]]]:
    geolocator = Nominatim(user_agent="food-drink-pairing-app")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
    coords = []
    for r in rows:
        query = r["address"] or f"서울 {r['name']}"
        try:
            loc = geocode(query)
            coords.append((loc.latitude, loc.longitude) if loc else (None, None))
        except Exception:
            coords.append((None, None))
        time.sleep(0.05)
    return coords

def build_html(row: Dict) -> str:
    html = f"""
    <div style="font-size:14px; line-height:1.55">
      <div style="font-weight:700">{EMOJI['식당']} {row['name']}</div>
      <div>{EMOJI['주소']} {row.get('address','')}</div>
      <div>{EMOJI['전화']} {row.get('phone','')}</div>
      <div>{EMOJI['평점']} {row.get('rating','-')}</div>
      <div>{EMOJI['링크']} <a href="{row.get('url','#')}" target="_blank">네이버 상세</a></div>
      <div style="margin-top:6px;color:#666">대표메뉴/가격은 네이버 상세에서 확인하는 게 제일 정확해요 🙌</div>
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

    # 1) 데이터 수집
    with st.spinner("네이버에서 찐 식당만 골라오는 중… 잠깐만! ⏳"):
        try:
            if cid and csec:
                rows = search_naver_local_api(gu, food, topk, cid, csec)
            else:
                rows = search_naver_scrape(gu, food, topk)
        except Exception as e:
            st.error(f"수집 중 오류: {e}")
            st.stop()

    # 2) 좌표
    coords = geocode_many(rows)
    for i, (lat, lon) in enumerate(coords):
        rows[i]["lat"] = lat
        rows[i]["lon"] = lon

    # 좌표가 하나도 없으면 안내
    if not any(r.get("lat") for r in rows):
        st.info("주소 좌표를 못 찾았어요 🥲  검색어를 조금 바꿔보거나, API 자격증명을 넣어주세요.")
        st.stop()

    # 3) 지도 만들기
    center_lat = next((r["lat"] for r in rows if r["lat"]), 37.5665)
    center_lon = next((r["lon"] for r in rows if r["lon"]), 126.9780)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13, tiles="CartoDB positron")

    for r in rows:
        if not r.get("lat") or not r.get("lon"):
            continue
        html = build_html(r)
        folium.Marker(
            location=[r["lat"], r["lon"]],
            tooltip=folium.Tooltip(html, sticky=True),  # 호버
            popup=folium.Popup(html, max_width=300),     # 클릭
            icon=folium.Icon(color="red", icon="cutlery", prefix="fa")
        ).add_to(m)

    st.success(f"**{gu}**에서 **{food}** 파는 곳 TOP{topk} 뽑아왔어요! 🙌 바로 지도에서 골라봐요👇")
    st_folium(m, width=None, height=560)

    # 4) 표도 같이 (옵션)
    df = pd.DataFrame(rows)
    show = df[["name","address","phone","rating","url"]].rename(
        columns={"name":"상호명","address":"주소","phone":"전화","rating":"평점","url":"링크"}
    )
    show.index = range(1, len(show)+1)
    st.dataframe(show, use_container_width=True)

else:
    st.info("왼쪽에서 **구 + 음식** 정하고 ‘식당 찾기’ 눌러줘! 뜨면 바로 지도 위에 마커로 쫙~ 찍어줄게 😎")
