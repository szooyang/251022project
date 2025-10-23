# pages/3_맛집_추천_봇.py
import json
import time
import pandas as pd
import streamlit as st

# OpenAI SDK (v1.x)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None

st.set_page_config(page_title="맛집 추천 봇", page_icon="🤖", layout="wide")
st.title("🤖 맛집 추천 봇 — OpenAI 키만 있으면 바로 GO!")
st.caption("키워드와 취향 입력 → AI가 동네/음식/무드 맞춘 맛집 아이디어를 뽑아줘요. (실시간 크롤링 X, 아이디어/초안 용)")

# -------------------------------------------------------------------
# 0) OpenAI 키: 시크릿에서만 읽기 (입력칸 제거)
# -------------------------------------------------------------------
DEFAULT_MODEL = "gpt-4o-mini"
api_key = st.secrets.get("OPENAI_API_KEY", "")

if not api_key:
    st.error("OpenAI API 키가 설정되어 있지 않습니다. Streamlit Secrets에 `OPENAI_API_KEY`를 추가해주세요.")
    st.stop()

model = st.selectbox("모델 선택", [DEFAULT_MODEL, "gpt-4o", "gpt-4.1-mini"], index=0, key="model_select")
temperature = st.slider("창의성(temperature)", 0.0, 1.2, 0.8, 0.1, key="temp_slider")

if "chat" not in st.session_state:
    st.session_state.chat = []
if "last_results" not in st.session_state:
    st.session_state.last_results = pd.DataFrame()

# -------------------------------------------------------------------
# 1) 컨텍스트 입력(메인 페이지의 음식 선택값 자동 연동)
# -------------------------------------------------------------------
default_food = st.session_state.get("selected_food", "")
SEOUL_GU = [
    "강남구","강동구","강북구","강서구","관악구","광진구","구로구","금천구","노원구","도봉구",
    "동대문구","동작구","마포구","서대문구","서초구","성동구","성북구","송파구","양천구","영등포구",
    "용산구","은평구","종로구","중구","중랑구"
]

with st.expander("🎛️ 추천 조건 세팅", expanded=True):
    c1, c2, c3 = st.columns([1,1,1])
    with c1:
        gu = st.selectbox("서울 **구**", SEOUL_GU, index=SEOUL_GU.index("강남구"), key="bot_gu")
    with c2:
        food = st.text_input("음식/키워드", value=str(default_food) or "비빔밥", key="bot_food")
    with c3:
        group_size = st.selectbox("인원", ["1-2명","3-4명","5-6명","7명 이상"], index=1, key="bot_group")

    c4, c5, c6 = st.columns([1,1,1])
    with c4:
        budget = st.select_slider("1인 예산", options=["<1만", "1~2만", "2~3만", "3~5만", "5만+"], value="1~2만", key="bot_budget")
    with c5:
        vibe = st.multiselect("무드", ["캐주얼","조용함","데이트","단체","술집","가성비","프리미엄"], default=["캐주얼"], key="bot_vibe")
    with c6:
        diet = st.multiselect("제한", ["매운맛 기피","채식","돼지고기 제외","소고기 제외","해산물 제외","견과류 알레르기"], key="bot_diet")

    c7, c8 = st.columns([1,1])
    with c7:
        need_reservation = st.checkbox("예약 편한 곳이면 좋음", value=False, key="bot_reserve")
    with c8:
        include_chains = st.checkbox("체인점도 OK", value=True, key="bot_chain")

st.write("---")

# -------------------------------------------------------------------
# 2) 시스템 프롬프트 (구조화 JSON)
# -------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are a restaurant recommendation assistant for Seoul. You do NOT browse the web.
Return diverse, plausible suggestions given the user's district and food keyword.
Respond STRICTLY as compact JSON with this schema:

{
  "summary": "one-line playful summary in Korean with emojis",
  "recommendations": [
    {
      "name": "string (Korean)",
      "area_hint": "string (동/로/랜드마크 등 간단 위치 힌트)",
      "category": "e.g., 한식/일식/중식/아시안/바/디저트",
      "signature_menu": "대표 메뉴 1-2개",
      "price_per_person": "예: 1.5만~2.5만",
      "fit_reason": "why this matches constraints (Korean, casual MZ tone)",
      "pro_tip": "ordering/seat/wait tips (Korean, short)",
      "search_query": "네이버/카카오에서 찾기 좋게 만든 한 줄 검색어"
    }
  ]
}

Rules:
- Do not invent exact addresses or phone numbers.
- Avoid hard facts like "Michelin 2024" unless very general.
- Give 5 items max.
- Mix well-known styles and indie vibes; avoid repeating same vibe.
- Use Korean (MZ tone) and fun emojis moderately.
"""

def build_user_prompt(gu, food, group_size, budget, vibe, diet, need_reservation, include_chains):
    return f"""\
구: {gu}
키워드(음식): {food}
인원: {group_size}
예산: {budget}
무드: {", ".join(vibe) if vibe else "무관"}
제한: {", ".join(diet) if diet else "없음"}
예약 선호: {"예" if need_reservation else "아니오"}
체인 허용: {"예" if include_chains else "아니오"}

요청:
- 위 조건을 만족하는 '서울 {gu}' 중심의 맛집 5곳 이내 추천
- 결과는 반드시 JSON (schema 준수)
- 각 항목마다 search_query 한 줄 포함 (사용자가 직접 검색해서 검증 가능)
"""

def chat_complete_json(api_key, model, messages, temperature=0.8, max_retries=2):
    if OpenAI is None:
        raise RuntimeError("openai 패키지가 필요합니다. requirements.txt에 openai>=1.30 추가하세요.")
    client = OpenAI(api_key=api_key)
    last_err = None
    for _ in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            last_err = e
            time.sleep(0.4)
    raise last_err

# -------------------------------------------------------------------
# 3) 채팅 UI
# -------------------------------------------------------------------
with st.container():
    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    user_msg = st.chat_input("원하는 분위기/동네 더 적어줘도 좋아요! (예: '매운 거 좋아' '압구정 쪽')")
    clicked = st.button("✨ 조건으로 추천 받기", use_container_width=True)

    if user_msg:
        st.session_state.chat.append({"role": "user", "content": user_msg})
        with st.chat_message("user"):
            st.markdown(user_msg)

    if clicked:
        sys = {"role": "system", "content": SYSTEM_PROMPT}
        context = {"role": "user", "content": build_user_prompt(
            gu, food, group_size, budget, vibe, diet, need_reservation, include_chains
        )}
        history_tail = st.session_state.chat[-6:] if len(st.session_state.chat) > 6 else st.session_state.chat

        with st.spinner("AI가 조건에 딱 맞는 후보 뽑는 중…😎"):
            try:
                data = chat_complete_json(
                    api_key=api_key,
                    model=model,
                    messages=[sys, context] + history_tail,
                    temperature=temperature,
                )
            except Exception as e:
                with st.chat_message("assistant"):
                    st.error(f"추천 생성 실패: {e}")
            else:
                summary = data.get("summary", "")
                recs = data.get("recommendations", [])[:5]

                with st.chat_message("assistant"):
                    if summary:
                        st.markdown(f"**{summary}**")
                    if not recs:
                        st.info("추천 결과가 비었어요. 키워드를 바꿔 다시 시도해볼까요?")
                    else:
                        rows = []
                        for r in recs:
                            name = r.get("name", "")
                            area = r.get("area_hint", "")
                            cat = r.get("category", "")
                            sig = r.get("signature_menu", "")
                            price = r.get("price_per_person", "")
                            why = r.get("fit_reason", "")
                            tip = r.get("pro_tip", "")
                            query = r.get("search_query", f"{gu} {food} 맛집")

                            st.markdown(
                                f"**🍽️ {name}** · {cat} · {area}\n\n"
                                f"- 시그니처: {sig}\n"
                                f"- 가격대: {price}\n"
                                f"- 왜 추천? {why}\n"
                                f"- 프로팁: {tip}\n"
                                f"- 🔎 검색어: `{query}`\n"
                            )
                            st.divider()

                            rows.append({
                                "이름": name, "구역힌트": area, "분류": cat,
                                "시그니처": sig, "1인예산": price,
                                "추천이유": why, "검색어": query
                            })

                        df = pd.DataFrame(rows)
                        st.session_state.last_results = df

                if 'data' in locals():
                    st.session_state.chat.append({"role": "assistant", "content": summary or "추천 결과가 생성되었습니다."})

# -------------------------------------------------------------------
# 4) 결과 내보내기 & 초기화
# -------------------------------------------------------------------
st.write("---")
cA, cB, cC = st.columns([1,1,1])
with cA:
    if not st.session_state.last_results.empty:
        csv = st.session_state.last_results.to_csv(index=False).encode("utf-8-sig")
        st.download_button("📥 추천 결과 CSV 다운로드", csv, file_name="맛집추천.csv", mime="text/csv", use_container_width=True)
with cB:
    if st.button("🧹 대화/결과 초기화", use_container_width=True):
        st.session_state.chat = []
        st.session_state.last_results = pd.DataFrame()
        st.rerun()
with cC:
    st.info("Tip) ‘검색어’를 복사해서 네이버/카카오 지도에 붙여넣으면 검증이 쉬워요!", icon="💡")
