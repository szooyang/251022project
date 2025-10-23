 # pages/3_맛집_추천_봇.py
import re, json, time, difflib
import requests
import pandas as pd
import streamlit as st
from urllib.parse import quote_plus

# ----------------- 기본 세팅 -----------------
st.set_page_config(page_title="맛집 추천 봇 – OpenAI만", page_icon="🔎", layout="wide")
st.title("🔎 맛집 추천 봇 — OpenAI 키만으로 ‘실검색 기반’ 추천")
st.caption("네이버 일반 검색 페이지를 가볍게 파싱해 실제 가게만 후보로 만들고, OpenAI는 요약/리랭크만 담당합니다. (타사 API 불필요)")

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", "")
if not OPENAI_KEY:
    st.error("OpenAI API 키가 없습니다. Streamlit Secrets에 `OPENAI_API_KEY`를 추가해주세요.")
    st.stop()

try:
    from openai import OpenAI
except Exception:
    st.error("`openai` 패키지가 필요합니다. requirements.txt에 `openai>=1.30` 추가 후 다시 배포하세요.")
    st.stop()

client = OpenAI(api_key=OPENAI_KEY)

# ----------------- 입력 UI -----------------
default_food = st.session_state.get("selected_food", "")
SEOUL_GU = [
    "강남구","강동구","강북구","강서구","관악구","광진구","구로구","금천구","노원구","도봉구",
    "동대문구","동작구","마포구","서대문구","서초구","성동구","성북구","송파구","양천구","영등포구",
    "용산구","은평구","종로구","중구","중랑구"
]

c1,c2,c3 = st.columns([1,1,1])
with c1:
    gu = st.selectbox("서울 **구**", SEOUL_GU, index=SEOUL_GU.index("강남구"))
with c2:
    food = st.text_input("음식/키워드", value=str(default_food) or "비빔밥")
with c3:
    topk = st.slider("최대 추천 수", 3, 10, 5)

st.write("---")
go = st.button("실검색으로 추천 받기 🚀", use_container_width=True)

# ----------------- 네이버 일반 검색 파서 -----------------
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/130.0.0.0 Safari/537.36")
}

def fetch_naver_serp(gu: str, food: str):
    """네이버 일반 검색 결과 HTML 텍스트(무키)"""
    q = f"{gu} {food} 식당"
    url = f"https://search.naver.com/search.naver?where=web&sm=tab_jum&query={quote_plus(q)}"
    # where=web: 일반 웹 결과 위주 (place 전용 DOM이 자주 바뀌므로 범용 파싱)
    r = requests.get(url, headers=HEADERS, timeout=10)
    r.raise_for_status()
    return r.text, q

def extract_candidates(html: str, q: str, max_items: int = 20):
    """
    HTML에서 상호/링크/스니펫을 유연하게 추출.
    - a href + 인접 텍스트를 긁어서 후보 생성
    - 상호명/쿼리 유사도 점수로 필터링
    반환: [{name, link, snippet, score}]
    """
    # 모든 a 태그 rough 추출
    links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.I|re.S)
    texts = []
    for href, inner_html in links:
        if not href.startswith("http"):
            continue
        title = re.sub("<.*?>", "", inner_html).strip()
        # 광고/스크립트/불필요 링크 대략 필터
        if not title or len(title) < 2: 
            continue
        if any(bad in href for bad in ["login", "policy", "javascript:", "naversearchad"]):
            continue
        texts.append((href, title))

    # 제목으로 1차 후보
    q_low = q.lower()
    cands = []
    seen = set()
    for href, title in texts:
        t = title.replace("\n"," ").strip()
        # 유사도 측정(쿼리 키워드 일부만으로 스코어)
        sim = difflib.SequenceMatcher(None, t.lower(), q_low).ratio()
        # "맛집", "식당" 같은 키워드/구명 포함 여부 가중
        bonus = 0.05 if ("맛집" in t or "식당" in t) else 0.0
        score = sim + bonus
        key = (t, href)
        if key not in seen:
            seen.add(key)
            # 간단한 스니펫: 타이틀 주변 텍스트를 추가로 뽑기(없으면 빈값)
            cands.append({"name": t, "link": href, "snippet": "", "score": score})

    # 스니펫 보강(간단히 title 텍스트 주변 문장을 추정)
    # 실제 DOM 파싱 없이 정규식으로 근처 텍스트를 찾아보는 라이트 접근
    for c in cands:
        # 타이틀 일부가 html에 들어있는 index 근처에서 120자 정도 추출 시도
        try:
            idx = html.find(c["name"])
            if idx != -1:
                start = max(0, idx - 100)
                end = min(len(html), idx + 200)
                snippet = re.sub("<.*?>", " ", html[start:end])
                snippet = re.sub(r"\s+", " ", snippet).strip()
                c["snippet"] = snippet[:160] + ("..." if len(snippet) > 160 else "")
        except Exception:
            pass

    # 점수 정렬 후 상위 반환
    cands.sort(key=lambda x: x["score"], reverse=True)
    return cands[:max_items]

# ----------------- OpenAI: 후보 리랭크/요약(새 가게 생성 금지) -----------------
SYS = (
    "You are a strict re-ranker/ summarizer. "
    "GIVEN ONLY the provided candidates from web search (with title/link/snippet), "
    "recommend top places. NEVER invent new restaurant names. "
    "Output compact JSON: {"
    '"summary":"Korean one-line with emojis", '
    '"items":[{"name":"string","reason":"Korean short","link":"url"}]'
    "} in Korean."
)

def ai_rerank(cands, topk):
    msg = {
        "role":"user",
        "content":(
            "아래는 네이버 웹검색에서 추출한 후보들입니다. "
            f"조건: 서울 {gu}, 키워드: {food}. "
            f"이 후보들만 가지고, 상위 {topk}개를 뽑아 간단 코멘트와 함께 JSON으로 반환하세요. "
            "새로운 상호명을 만들면 안 됩니다.\n\n"
            + json.dumps(cands, ensure_ascii=False)
        )
    }
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"system","content":SYS}, msg],
        response_format={"type":"json_object"},
        temperature=0.2
    )
    return json.loads(resp.choices[0].message.content)

# ----------------- 실행 -----------------
if go:
    if not food.strip():
        st.warning("음식/키워드를 입력해 주세요!")
        st.stop()

    with st.spinner("네이버에서 실제 결과를 긁어와 후보 만드는 중…"):
        try:
            html, query = fetch_naver_serp(gu, food)
            candidates = extract_candidates(html, query, max_items=30)
        except Exception as e:
            st.error(f"검색 페이지 수집 실패: {e}")
            st.stop()

    if not candidates:
        st.info("후보를 찾지 못했어요 🥲  키워드를 바꿔보거나 좀 더 일반적인 표현을 써볼까요?")
        st.stop()

    # 후보를 OpenAI로 리랭크/요약(새 가게 생성 금지)
    with st.spinner("AI가 후보만 가지고 안전하게 리랭크 중…"):
        try:
            ai = ai_rerank(
                [{"name": c["name"], "link": c["link"], "snippet": c["snippet"]} for c in candidates],
                topk=topk
            )
        except Exception as e:
            st.error(f"AI 요약 실패: {e}")
            st.stop()

    summary = ai.get("summary","")
    items = ai.get("items", [])[:topk]

    # 결과 표
    st.success(f"**{gu} · {food}** 실검색 기반 추천 TOP{len(items)}")
    rows = []
    for it in items:
        name, reason, link = it.get("name",""), it.get("reason",""), it.get("link","#")
        # 원 후보에서 간단 스니펫 매칭
        snip = next((c["snippet"] for c in candidates if c["name"]==name and c["link"]==link), "")
        st.markdown(f"**🍽️ {name}**  \n- {reason}\n- 🔗 [링크]({link})")
        if snip:
            st.caption(snip)
        st.divider()
        rows.append({"이름":name, "코멘트":reason, "링크":link, "스니펫":snip})

    df = pd.DataFrame(rows)
    df.index = range(1, len(df)+1)
    st.dataframe(df, use_container_width=True)

    if summary:
        st.subheader("🤖 한 줄 요약")
        st.markdown(summary)

    # 다운로드
    csv = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button("📥 CSV 다운로드", csv, file_name="openai_only_recommendations.csv", use_container_width=True)

else:
    st.info("구/키워드/개수 정하고 ‘실검색으로 추천 받기’ 버튼을 눌러주세요. OpenAI 키만으로 동작합니다 🙂")
