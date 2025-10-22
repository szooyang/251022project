import streamlit as st
import pandas as pd
import time
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import folium
from streamlit_folium import st_folium

st.set_page_config(page_title="식당 추천", page_icon="🍽️", layout="wide")
st.title("🍜 식당 추천 (서울) — MZ 감성 버전 ✨")
st.caption("네이버에서 실시간으로 찾아온 TOP5! 지도를 호버하면 대표메뉴/가격도 슥~ 보여줄게요 😎")

# ---------------------------------------
# 공용 설정
# ---------------------------------------
SEOUL_GU = [
    "강남구","강동구","강북구","강서구","관악구","광진구","구로구","금천구","노원구","도봉구",
    "동대문구","동작구","마포구","서대문구","서초구","성동구","성북구","송파구","양천구","영등포구",
    "용산구","은평구","종로구","중구","중랑구"
]

EMOJI = {"식당":"🍽️","주소":"📍","전화":"📞","평점":"⭐️","메뉴":"📋","링크":"🔗"}

# 세션에서 음식 기본값 읽기
default_food = st.session_state.get("selected_food", "")
colA, colB = st.columns([1,1])
with colA:
    gu = st.selectbox("서울시 **구**를 골라주세요", SEOUL_GU, index=SEOUL_GU.index("강남구"))
with colB:
    food = st.text_input("무슨 음식 찾을까요? (메인 페이지 선택값 자동 연동)", value=str(default_food) or "")

go = st.button("🔎 식당 찾기")

st.write("---")

# ---------------------------------------
# 네이버 로컬 검색 (상위 5곳)
# ---------------------------------------
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
}

def search_naver_local(gu: str, food: str, topk: int = 5):
    """
    네이버 '지역(where=local)' 결과 파싱 (가벼운 HTML 파서).
    반환: [{name, address, phone, rating, url, menu_snippet}]
    """
    q = f"{gu} {food} 식당"
    url = f"https://search.naver.com/search.naver?where=local&query={quote_plus(q)}"
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")

    # 결과 블록 후보들: 구조가 자주 바뀌므로 넓게 탐색하고 키워드로 필터
    items = []
    # 리스트형 결과 카드 a태그 후보 수집
    for a in soup.select("a"):
        href = a.get("href", "")
        # 네이버플레이스/지도 링크만 선별
        if "map.naver.com" in href or "place.naver.com" in href:
            name = a.get_text(strip=True)
            # 너무 짧거나 광고/불필요 링크 스킵
            if not name or len(name) < 2:
                continue
            items.append((name, href))

    # 유니크로 정리
    seen = set()
    uniq = []
    for name, href in items:
        key = (name, href)
        if key in seen: 
            continue
        seen.add(key)
        uniq.append((name, href))

    # 추가 정보(주소/전화/평점/메뉴 스니펫) 추출: 주변 텍스트에서 힌트를 모아봄
    results = []
    for name, href in uniq:
        # 주변 텍스트에서 주소/평점/전화 후보 텍스트 모으기
        # 간단히 name이 들어간 인접 노드들을 검색(유연한 방식)
        address = phone = rating = menu_snippet = ""
        # 주소 패턴 힌트
        addr_candidates = soup.find_all(string=re.compile(r"(서울|동|로|길|구|번지)"))
        if addr_candidates:
            address = str(addr_candidates[0]).strip()[:60]

        # 평점 후보
        rating_candidates = soup.find_all(string=re.compile(r"평점|리뷰|별|[0-9]\.?[0-9]\s*/\s*5"))
        if rating_candidates:
            rating = re.findall(r"([0-9]\.?[0-9])\s*/\s*5", rating_candidates[0])
            rating = rating[0] if rating else rating_candidates[0].strip()[:20]

        # 전화 후보
        phone_candidates = soup.find_all(string=re.compile(r"0\d{1,2}-\d{3,4}-\d{4}"))
        if phone_candidates:
            phone = phone_candidates[0].strip()

        # 메뉴/가격 스니펫 후보
        menu_candidates = soup.find_all(string=re.compile(r"(메뉴|가격|대표메뉴|원)"))
        if menu_candidates:
            menu_snippet = str(menu_candidates[0]).strip()[:60]

        results.append({
            "name": name,
            "address": address,
            "phone": phone,
            "rating": rating,
            "url": href
        })
        # 상위 topk만
        if len(results) >= topk:
            break

    return results

# ---------------------------------------
# 지오코딩 (OSM Nominatim)
# ---------------------------------------
@st.cache_data(show_spinner=False)
def geocode_many(rows, gu):
    geolocator = Nominatim(user_agent="food-drink-pairing-app")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1)
    coords = []
    for r in rows:
        # 주소가 너무 빈약하면 "서울 {구} {상호}"로 지오코딩 시도
        query = r["address"] or f"서울 {gu} {r['name']}"
        try:
            loc = geocode(query)
            if loc:
                coords.append((loc.latitude, loc.longitude))
            else:
                coords.append((None, None))
        except Exception:
            coords.append((None, None))
        time.sleep(0.1)
    return coords

def build_tooltip_html(row):
    name = row["name"]
    addr = row.get("address") or "주소 정보 준비중"
    phone = row.get("phone") or "번호 정보 없음"
    rating = row.get("rating") or "-"
    url = row.get("url") or "#"

    html = f"""
    <div style="font-size:14px; line-height:1.5">
      <div style="font-weight:700">{EMOJI['식당']} {name}</div>
      <div>{EMOJI['주소']} {addr}</div>
      <div>{EMOJI['전화']} {phone}</div>
      <div>{EMOJI['평점']} {rating}</div>
      <div>{EMOJI['링크']} <a href="{url}" target="_blank">네이버 상세</a></div>
      <div style="margin-top:6px; color:#666">※ 대표메뉴/가격은 네이버 상세페이지에서 확인이 더 정확해요!</div>
    </div>
    """
    return html

# ---------------------------------------
# 실행
# ---------------------------------------
if go:
    if not food.strip():
        st.warning("음식명을 입력해줘요! 예: 김치볶음밥, 비빔밥 등 🙂")
        st.stop()

    with st.spinner("네이버에 물어보고 있어요… (조금만!)"):
        rows = search_naver_local(gu, food, topk=5)

    if not rows:
        st.info("앗, 결과가 없네요. 음식명을 좀 더 구체적으로 입력해볼까요? 예: 비빔밥 → 전주비빔밥")
        st.stop()

    df = pd.DataFrame(rows)
    st.success(f"**{gu}**에서 **{food}** 파는 곳 TOP5 뽑아왔어요! 🙌")
    st.dataframe(df[["name","address","phone","rating","url"]].rename(
        columns={"name":"상호명","address":"주소","phone":"전화","rating":"평점","url":"링크"}
    ), use_container_width=True)

    # 지도 만들기
    coords = geocode_many(rows, gu)
    for i, (lat, lon) in enumerate(coords):
        rows[i]["lat"] = lat
        rows[i]["lon"] = lon

    # 중심 좌표
    center_lat = next((r["lat"] for r in rows if r["lat"]), 37.5665)
    center_lon = next((r["lon"] for r in rows if r["lon"]), 126.9780)

    m = folium.Map(location=[center_lat, center_lon], zoom_start=13, tiles="CartoDB positron")

    for r in rows:
        if not r["lat"] or not r["lon"]:
            continue
        tooltip_html = build_tooltip_html(r)  # hover 시 보여줄 내용
        folium.Marker(
            location=[r["lat"], r["lon"]],
            tooltip=folium.Tooltip(tooltip_html, sticky=True),  # ← 호버 툴팁
            popup=folium.Popup(tooltip_html, max_width=300),
            icon=folium.Icon(color="red", icon="cutlery", prefix="fa")
        ).add_to(m)

    st_folium(m, width=None, height=520)
    st.caption("Tip) 장소를 탭하면 팝업으로도 정보가 떠요. 링크 눌러서 바로 네이버 디테일 GO! 💨")

else:
    st.info("왼쪽에서 **구**랑 **음식** 정하고, 위의 **검색** 버튼을 눌러주세요! 🚀")
