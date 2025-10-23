# pages/5_블로거_맛집_추천.py
# ─────────────────────────────────────────────────────────────────────
# 블로거 맛집 추천 — OpenAI 키만으로 '실검색 기반' 추천
# (네이버 VIEW/블로그 결과를 우선 파싱 → 후보를 OpenAI가 리랭크/요약)
# ─────────────────────────────────────────────────────────────────────

import re, json, difflib
import requests
import pandas as pd
import streamlit as st
from urllib.parse import quote_plus, urlparse

# ── 페이지 설정 ─────────────────────────────────────────────────────
st.set_page_config(page_title="블로거 맛집 추천", page_icon="📝", layout="wide")
st.title("📝 블로거 맛집 추천 — OpenAI 키만으로 ‘실검색 기반’")
st.caption("네이버 VIEW(블로그/카페) 검색 결과를 가볍게 파싱해 실제 링크가 있는 후보만 모으고, OpenAI는 리랭크/요약만 담당합니다. (타사 API 불필요)")

# ── OpenAI 준비 (Secrets에서만 읽음) ─────────────────────────────────
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
if not OPENAI_KEY:
    st.error("OpenAI API 키가 없습니다. Streamlit Secrets에 `OPENAI_API_KEY`를 추가해주세요.")
    st.stop()

try:
    from openai import OpenAI
except Exception:
    st.error("`openai` 패키지가 필요합니다. requirements.txt에 `openai>=1.30` 추가 후 재배포하세요.")
    st.stop()

client = OpenAI(api_key=OPENAI_KEY)

# ── 입력 UI ──────────────────────────────────────────────────────────
default_food = st.session_state.get("selected_food", "")
SEOUL_GU = [
    "강남구","강동구","강북구","강서구","관악구","광진구","구로구","금천구","노원구","도봉구",
    "동대문구","동작구","마포구","서대문구","서초구","성동구","성북구","송파구","양천구","영등포구",
    "용산구","은평구","종로구","중구","중랑구"
]

c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    gu = st.selectbox("서울 **구**", SEOUL_GU, index=SEOUL_GU.index("강남구"), key="blog_gu")
with c2:
    food = st.text_input("음식/키워드", value=str(default_food) or "비빔밥", key="blog_food")
with c3:
    topk = st.slider("최대 추천 수", 3, 10, 5, key="blog_topk")

st.write("---")
go = st.button("블로그 기반으로 추천 받기 🚀", use_container_width=True, key="blog_go")

# ── 네이버 VIEW/WEB 파서(무키) ───────────────────────────────────────
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
}
BLOG_DOMAINS = ("blog.naver.com", "m.blog.naver.com", "tistory.com", "brunch.co.kr")

def fetch_naver_serp(mode: str, gu: str, food: str):
    """
    mode: 'view' (블로그/카페 중심) 또는 'web' (일반 웹)
    """
    if mode == "view":
        q = f"{gu} {food} 맛집 후기"
        url = f"https://search.naver.com/search.naver?where=view&sm=tab_jum&query={quote_plus(q)}"
    else:
        q = f"{gu} {food} 맛집"
        url = f"https://search.naver.com/search.naver?where=web&sm=tab_jum&query={quote_plus(q)}"
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.text, q

def extract_candidates(html: str, q: str, max_items: int = 24, prefer_blogs: bool = True):
    """
    HTML에서 제목/링크를 유연하게 추출해 후보 리스트로 반환.
    반환 요소: [{name, link, snippet, score}]
    - 블로그/티스토리/브런치 도메인은 가중치 부여
    """
    # 모든 a 태그 rough 추출
    raw = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.I | re.S)
    pairs = []
    for href, inner in raw:
        if not href.startswith("http"):
            continue
        title = re.sub("<.*?>", "", inner).strip()
        if not title or len(title) < 2:
            continue
        if any(bad in href for bad in ["login", "policy", "javascript:", "naversearchad"]):
            continue
        pairs.append((href, title))

    # 유사도 기반 후보화
    cands, seen = [], set()
    q_low = q.lower()
    for href, title in pairs:
        t = title.replace("\n", " ").strip()
        sim = difflib.SequenceMatcher(None, t.lower(), q_low).ratio()

        # 키워드/구/맛집 관련 가중
        bonus_kw = 0.05 if any(k in t for k in ["맛집", "식당", "후기", "리뷰"]) else 0.0
        # 블로그 도메인 가중
        host = urlparse(href).netloc.lower()
        bonus_blog = 0.10 if (prefer_blogs and any(d in host for d in BLOG_DOMAINS)) else 0.0

        score = sim + bonus_kw + bonus_blog
        key = (t, href)
        if key not in seen:
            seen.add(key)
            cands.append({"name": t, "link": href, "snippet": "", "score": score})

    # 타이틀 주변 텍스트를 간단 스니펫으로
    for c in cands:
        try:
            idx = html.find(c["name"])
            if idx != -1:
                start = max(0, idx - 100)
                end = min(len(html), idx + 200)
                snippet = re.sub("<.*?>", " ", html[start:end])
                snippet = re.sub(r"\s+", " ", snippet).strip()
                c["snippet"] = (snippet[:160] + "...") if len(snippet) > 160 else snippet
        except Exception:
            pass

    cands.sort(key=lambda x: x["score"], reverse=True)
    return cands[:max_items]

# ── OpenAI: 후보 리랭크/요약(새 가게 생성 금지) ──────────────────────
SYS = (
    "You are a strict re-ranker/summarizer. "
    "GIVEN ONLY the provided candidates from web search (with title/link/snippet), "
    "recommend top places. NEVER invent new restaurant names. "
    "Output compact JSON: {"
    '"summary":"Korean one-line with emojis", '
    '"items":[{"name":"string","reason":"Korean short","link":"url"}]'
    "} in Korean."
)

def ai_rerank(cands, topn):
    prompt = {
        "role": "user",
        "content": (
            "아래는 네이버 VIEW/블로그 검색에서 추출한 후보들입니다. "
            f"조건: 서울 {gu}, 키워드: {food}. "
            f"이 후보들만 가지고, 상위 {topn}개를 뽑아 간단 코멘트와 함께 JSON으로 반환하세요. "
            "새로운 상호명을 만들면 안 됩니다.\n\n"
            + json.dumps(cands, ensure_ascii=False)
        ),
    }
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": SYS}, prompt],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    return json.loads(resp.choices[0].message.content)

# ── 실행 ─────────────────────────────────────────────────────────────
if go:
    if not food.strip():
        st.warning("음식/키워드를 입력해 주세요!")
        st.stop()

    # 1) VIEW(블로그/카페) 우선
    with st.spinner("네이버 VIEW(블로그/카페)에서 후보 수집 중…"):
        try:
            html, query = fetch_naver_serp("view", gu, food)
            candidates = extract_candidates(html, query, max_items=30, prefer_blogs=True)
        except Exception as e:
            st.info(f"VIEW 수집 실패, 일반 웹으로 대체합니다: {e}")
            candidates = []

    # 2) VIEW에서 충분치 않으면 WEB로 보강
    if not candidates:
        with st.spinner("네이버 WEB(일반)에서 후보 수집 중…"):
            try:
                html, query = fet
