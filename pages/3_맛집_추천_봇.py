# pages/3_맛집_추천_봇.py
import time
import json
import re
import difflib
import requests
import pandas as pd
import streamlit as st
from urllib.parse import quote_plus

# ============== 기본 세팅 ==============
st.set_page_config(page_title="맛집 추천 봇 – 리얼서치", page_icon="🔎", layout="wide")
st.title("🔎 맛집 추천 봇 — 리얼서치 기반 (거짓 제로 지향)")
st.caption("실시간 검색 결과로만 추천합니다. (카카오 키가 있으면 사용, 없으면 키 없이도 동작)")

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
KAKAO_KEY  = st.secrets.get("KAKAO_REST_KEY", "")

# OpenAI (요약/코멘트 전용)
try:
    from openai import OpenAI
    _openai_ok = True
except Exception:
    _openai_ok = False

# ============== 컨트롤 ==============
default_food = st.session_state.get("selected_food", "")
SEOUL_GU = [
    "강남구","강동구","강북구","강서구","관악구","광진구","구로구","금천구","노원구","도봉구",
    "동대문구","동작구","마포구","서대문구","서초구","성동구","성북구","송파구","양천구","영등포구",
    "용산구","은평구","종로구","중구","중랑구"
]
c1, c2, c3 = st.columns([1,1,1])
with c1:
    gu = st.selectbox("서울 **구**", SEOUL_GU, index=SEOUL_GU.index("강남구"))
with c2:
    food = st.text_input("음식/키워드", value=str(default_food) or "비빔밥")
with c3:
    topk = st.slider("최대 추천 수", 3, 10, 5)

go = st.button("실시간으로 찾기 🚀", use_container_width=True)
st.write("---")

# ============== 수집기 ==============

# 1) Kakao Local (있으면 사용)
KAKAO_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

def kakao_search_places(rest_key: str, gu: str, food: str, size: int):
    headers = {"Authorization": f"KakaoAK {rest_key}"}
    q = f"{gu} {food} 식당"
    params = {"query": q, "category_group_code": "FD6", "size": size, "page": 1}
    r = requests.get(KAKAO_URL, headers=headers, params=params, timeout=10)
    r.raise_for_status()
    docs = r.json().get("documents", [])
    out = []
    for d in docs:
        out.append({
            "name": d.get("place_name",""),
            "road_address": d.get("road_address_name",""),
            "address": d.get("address_name",""),
            "phone": d.get("phone",""),
            "url": d.get("place_url",""),
            "lat": float(d["y"]) if d.get("y") else None,
            "lon": float(d["x"]) if d.get("x") else None,
            "source": "kakao"
        })
    return out

# 2) Overpass(키 없이 후보) → 후검증으로 실존 필터
OVERPASS = "https://overpass-api.de/api/interpreter"

def overpass_candidates(gu: str, food: str, size: int):
    food_esc = re.sub(r'(["\\])', r"\\\1", food)
    q = f"""
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
    out center {size*3};   /* 여유로 가져와서 검증단계에서 추림 */
    """
    r = requests.post(OVERPASS, data={"data": q}, timeout=30)
    r.raise_for_status()
    elements = r.json().get("elements", [])
    out = []
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name:ko") or tags.get("name") or ""
        addr = tags.get("addr:full") or " ".join(
            filter(None, [tags.get("addr:city"), tags.get("addr:district"),
                          tags.get("addr:street"), tags.get("addr:housenumber")])
        )
        lat = el.get("lat") or (el.get("center") or {}).get("lat")
        lon = el.get("lon") or (el.get("center") or {}).get("lon")
        if name and lat and lon:
            out.append({
                "name": name, "road_address": addr, "address": addr,
                "phone": "", "url": "", "lat": lat, "lon": lon, "source": "osm"
            })
    return out[: size*3]

# 3) 네이버 웹검색(일반)으로 실존 검증
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/130.0.0.0 Safari/537.36")
}

def naver_web_validate(name: str, gu: str, food: str):
    """네이버 일반 검색 상위 결과에서 상호 포함 여부 확인 후 링크/타이틀/스니펫 반환"""
    q = f"{gu} {name} {food}"
    url = f"https://search.naver.com/search.naver?query={quote_plus(q)}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except Exception:
        return None

    # 단순 a태그 추출 + 필터링
    titles, links = [], []
    for a in re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', r.text, flags=re.I|re.S):
        href, title_html = a
        title = re.sub("<.*?>", "", title_html)
        if not title or not href.startswith("http"):
            continue
        # 블로그/뉴스/광고 등 섞임 → 상호명 유사도 기반으로 필터
        ratio = difflib.SequenceMatcher(None, title.lower(), name.lower()).ratio()
        if ratio >= 0.45 or name.lower() in title.lower():
            links.append(href)
            titles.append(title)
        if len(links) >= 3:
            break

    if not links:
        return None
    return {"title": titles[0], "link": links[0]}

# 4) OpenAI로 “요약/코멘트”만 생성 (리랭크 허용, 새 가게 생성 금지)
SYS = """You summarize and lightly re-rank *existing* restaurant candidates.
Never invent new places. Output Korean, playful but concise."""

def ai_comment(cands, key):
    if not _openai_ok or not key or not cands:
        return None
    client = OpenAI(api_key=key)
    prompt = {
        "role":"user",
        "content":(
            "아래 후보(이름/출처/검증링크)를 바탕으로 상위 5곳 이내를 한 줄 요약과 함께 추천해줘. "
            "새 가게를 만들지 말고, 주어진 후보만 재정렬하고 코멘트를 붙여. "
            "JSON으로만 응답해: [{name, reason, link}].\n\n" + json.dumps(cands, ensure_ascii=False)
        )
    }
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role":"system","content":SYS}, prompt],
            response_format={"type":"json_object"},
            temperature=0.3
        )
        data = json.loads(resp.choices[0].message.content)
        return data
    except Exception:
        return None

# ============== 실행 ==============
if go:
    if not food.strip():
        st.warning("음식 키워드를 입력해 주세요!")
        st.stop()

    rows = []
    # 1) Kakao 우선
    if KAKAO_KEY:
        with st.spinner("카카오에서 실데이터 수집 중…"):
            try:
                rows = kakao_search_places(KAKAO_KEY, gu, food, size=topk*2)
            except Exception as e:
                st.info(f"Kakao 수집 실패(키/쿼터 문제일 수 있어요): {e}")

    # 2) 없으면 OSM 후보
    if not rows:
        with st.spinner("키 없이(오픈스트리트맵) 후보 수집 중…"):
            try:
                rows = overpass_candidates(gu, food, size=topk)
            except Exception as e:
                st.error(f"키 없이 후보 수집 실패: {e}")
                st.stop()

    # 3) 네이버 웹검색으로 실제 확인 + 링크 부여
    verified = []
    with st.spinner("네이버 웹검색으로 실존 검증 중…"):
        for r in rows:
            v = naver_web_validate(r["name"], gu, food)
            if v:
                r["verified_link"] = v["link"]
                r["verified_title"] = v["title"]
                verified.append(r)
            if len(verified) >= topk:
                break

    if not verified:
        st.info("검증된 결과가 없어요 🥲 키워드를 더 넓게 적거나 다른 구를 시도해보세요.")
        st.stop()

    # 4) OpenAI로 ‘요약/리랭크’ (선택)
    summary = None
    if OPENAI_KEY:
        payload = [{"name": r["name"], "source": r["source"], "link": r.get("verified_link","")} for r in verified]
        ai = ai_comment(payload, OPENAI_KEY)
        if ai and isinstance(ai, dict):
            summary = ai

    # 5) 출력
    st.success(f"**{gu} · {food}** 실검색 기반 추천 TOP{len(verified)}")
    cols = ["name","road_address","address","phone","verified_title","verified_link"]
    show = pd.DataFrame([{k: v for k, v in r.items() if k in cols} for r in verified]) \
            .rename(columns={"name":"상호명","road_address":"도로명주소","address":"지번주소",
                             "phone":"전화","verified_title":"검증제목","verified_link":"검증링크"})
    show.index = range(1, len(show)+1)
    st.dataframe(show, use_container_width=True)

    for r in verified:
        link = r.get("verified_link","#")
        title = r.get("verified_title","")
        st.markdown(f"**🍽️ {r['name']}**  ·  [{title}]({link})")

    st.write("---")
    if summary and "items" in summary or isinstance(summary, list):
        st.subheader("🤖 요약 & 리랭크 (AI)")
        try:
            items = summary.get("items", summary)  # 둘 중 하나 형태
            for it in items[:topk]:
                st.markdown(f"- **{it.get('name','')}** — {it.get('reason','')}  🔗 {it.get('link','')}")
        except Exception:
            pass

    # 다운로드
    csv = show.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 CSV 다운로드", csv, file_name="realsearch_restaurants.csv", mime="text/csv", use_container_width=True)

else:
    st.info("구/키워드/개수 정하고 ‘실시간으로 찾기’ 버튼을 눌러주세요! 결과는 실데이터 기반으로만 보여드려요 🙂")
