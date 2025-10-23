# pages/4_블로거_맛집_추천.py
# 블로거 맛집 추천 — OpenAI 키만으로 '실검색 기반' 추천
# (네이버 VIEW/웹 검색을 파싱해 후보를 만들고, OpenAI는 리랭크/요약만 수행)

import re
import json
import difflib
import requests
import pandas as pd
import streamlit as st
from urllib.parse import quote_plus, urlparse

# 페이지 설정
st.set_page_config(page_title="블로거 맛집 추천", page_icon="📝", layout="wide")
st.title("📝 블로거 맛집 추천 — OpenAI 키만으로 ‘실검색 기반’")
st.caption(
    "네이버 VIEW(블로그/카페) 검색 결과를 가볍게 파싱해 실제 링크가 있는 후보만 모으고, "
    "OpenAI는 리랭크/요약만 담당합니다. (타사 API 불필요)"
)

# OpenAI 준비 (Secrets에서만 읽음)
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
if not OPENAI_KEY:
    st.error("OpenAI API 키가 없습니다. Streamlit Secrets에 OPENAI_API_KEY를 추가해주세요.")
    st.stop()

try:
    from openai import OpenAI
except Exception:
    st.error("openai 패키지가 필요합니다. requirements.txt에 openai>=1.30 추가 후 재배포하세요.")
    st.stop()

client = OpenAI(api_key=OPENAI_KEY)

# 입력 UI
default_food = st.session_state.get("selected_food", "")
SEOUL_GU = [
    "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구", "노원구", "도봉구",
    "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구", "성북구", "송파구", "양천구", "영등포구",
    "용산구", "은평구", "종로구", "중구", "중랑구"
]

c1, c2, c3 = st.columns([1, 1, 1])
with c1:
    gu = st.selectbox("서울 구", SEOUL_GU, index=SEOUL_GU.index("강남구"), key="blog_gu")
with c2:
    food = st.text_input("음식/키워드", value=str(default_food) or "비빔밥", key="blog_food")
with c3:
    topk = st.slider("최대 추천 수", min_value=3, max_value=10, value=5, step=1, key="blog_topk")

st.write("---")
go = st.button("블로그 기반으로 추천 받기 🚀", use_container_width=True, key="blog_go")

# 네이버 VIEW/WEB 파서(무키)
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36"
    )
}
BLOG_DOMAINS = ("blog.naver.com", "m.blog.naver.com", "tistory.com", "brunch.co.kr")

def fetch_naver_serp(mode: str, gu_name: str, food_kw: str):
    """
    mode: 'view' (블로그/카페 중심) 또는 'web' (일반 웹)
    """
    if mode == "view":
        q = f"{gu_name} {food_kw} 맛집 후기"
        url = (
            "https://search.naver.com/search.naver"
            f"?where=view&sm=tab_jum&query={quote_plus(q)}"
        )
    else:
        q = f"{gu_name} {food_kw} 맛집"
        url = (
            "https://search.naver.com/search.naver"
            f"?where=web&sm=tab_jum&query={quote_plus(q)}"
        )
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.text, q

def extract_candidates(html: str, q: str, max_items: int = 24, prefer_blogs: bool = True):
    """
    HTML에서 제목/링크를 추출해 후보 리스트 반환.
    반환: [{name, link, snippet, score}]
    - 블로그/티스토리/브런치 도메인 가중치 부여
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
    cands = []
    seen = set()
    q_low = q.lower()
    for href, title in pairs:
        t = title.replace("\n", " ").strip()
        sim = difflib.SequenceMatcher(None, t.lower(), q_low).ratio()

        bonus_kw = 0.05 if any(k in t for k in ["맛집", "식당", "후기", "리뷰"]) else 0.0
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
                if len(snippet) > 160:
                    snippet = snippet[:160] + "..."
                c["snippet"] = snippet
        except Exception:
            pass

    cands.sort(key=lambda x: x["score"], reverse=True)
    return cands[:max_items]

# OpenAI: 후보 리랭크/요약(새 가게 생성 금지)
SYS = (
    "You are a strict re-ranker/summarizer. "
    "GIVEN ONLY the provided candidates from web search (with title/link/snippet), "
    "recommend top places. NEVER invent new restaurant names. "
    "Output compact JSON: {"
    "\"summary\":\"Korean one-line with emojis\", "
    "\"items\":[{\"name\":\"string\",\"reason\":\"Korean short\",\"link\":\"url\"}]"
    "} in Korean."
)

def ai_rerank(cands, topn: int):
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

# 실행
if go:
    if not food.strip():
        st.warning("음식/키워드를 입력해 주세요!")
        st.stop()

    # 1) VIEW(블로그/카페) 우선
    try:
        with st.spinner("네이버 VIEW(블로그/카페)에서 후보 수집 중…"):
            html_view, query = fetch_naver_serp("view", gu, food)
            candidates = extract_candidates(html_view, query, max_items=30, prefer_blogs=True)
    except Exception as e:
        st.info(f"VIEW 수집 실패, 일반 웹으로 대체합니다: {e}")
        candidates = []

    # 2) 부족하면 WEB 보강
    if not candidates:
        try:
            with st.spinner("네이버 WEB(일반)에서 후보 수집 중…"):
                html_web, query_web = fetch_naver_serp("web", gu, food)
                candidates = extract_candidates(html_web, query_web, max_items=30, prefer_blogs=False)
        except Exception as e:
            st.error(f"검색 페이지 수집 실패: {e}")
            st.stop()

    if not candidates:
        st.info("후보를 찾지 못했어요. 키워드를 바꾸거나 더 일반적인 표현으로 시도해 주세요.")
        st.stop()

    # 3) OpenAI 리랭크/요약 (생성 금지)
    try:
        with st.spinner("AI가 블로거 후보들만 가지고 안전하게 리랭크 중…"):
            ai = ai_rerank(
                [{"name": c["name"], "link": c["link"], "snippet": c["snippet"]} for c in candidates],
                topn=topk,
            )
    except Exception as e:
        st.error(f"AI 요약 실패: {e}")
        st.stop()

    summary = ai.get("summary", "")
    items = ai.get("items", [])[:topk]

    st.success(f"{gu} · {food} — 블로거 기반 추천 TOP{len(items)}")

    rows = []
    for it in items:
        name = it.get("name", "")
        reason = it.get("reason", "")
        link = it.get("link", "#")
        snip = ""
        for c in candidates:
            if c["name"] == name and c["link"] == link:
                snip = c.get("snippet", "")
                break

        st.markdown(f"**🍽️ {name}**\n- {reason}\n- 🔗 [링크]({link})")
        if snip:
            st.caption(snip)
        st.divider()

        rows.append({"이름": name, "코멘트": reason, "링크": link, "스니펫": snip})

    df = pd.DataFrame(rows)
    df.index = range(1, len(df) + 1)
    st.dataframe(df, use_container_width=True)

    if summary:
        st.subheader("🤖 한 줄 요약")
        st.markdown(summary)

    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        label="📥 CSV 다운로드",
        data=csv,
        file_name="blogger_based_recommendations.csv",
        mime="text/csv",
        use_container_width=True,
    )

else:
    st.info("구/키워드/개수 정하고 ‘블로그 기반으로 추천 받기’ 버튼을 눌러주세요. OpenAI 키만으로 동작합니다.")
