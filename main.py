import streamlit as st
import pandas as pd
import plotly.express as px
from google import genai
import json

# ----------------------------------------------------
# 0. 설정 및 데이터 로드
# ----------------------------------------------------

# --- 상수 설정 ---
TOP_N_FOOD = 10 
SEOUL_GUS = [
    "강남구", "강동구", "강북구", "강서구", "관악구", "광진구", "구로구", "금천구", 
    "노원구", "도봉구", "동대문구", "동작구", "마포구", "서대문구", "서초구", "성동구", 
    "성북구", "송파구", "양천구", "영등포구", "용산구", "은평구", "종로구", "중구", "중랑구"
]
EMOJIS_DRINKS = {
    "소주": "🍶", "맥주": "🍺", "와인": "🍷", "막걸리": "🥛", "위스키": "🥃", 
    "칵테일": "🍸", "사케": "🍶"
}

# --- 데이터 불러오기 ---
@st.cache_data
def load_data():
    """데이터를 불러오고 필요한 술 컬럼 목록을 반환합니다."""
    try:
        # 파일명은 'food_drink_pairings.csv'로 가정
        df = pd.read_csv("food_drink_pairings.csv")
    except FileNotFoundError:
        st.error("⚠️ food_drink_pairings.csv 파일을 찾을 수 없습니다. 파일을 업로드하거나 경로를 확인하세요.")
        return pd.DataFrame(), []

    drink_cols = [col for col in df.columns if col not in ["음식군", "대표음식"]]
    return df, drink_cols

df, DRINKS = load_data()

st.set_page_config(page_title="🍶 음식 & 술 궁합 대시보드", page_icon="🍽️", layout="centered")

# Gemini 클라이언트 초기화 (Streamlit Cloud 환경에서는 API 키가 자동 주입됨)
# gemini-2.5-flash 모델은 Google Search grounding을 지원합니다.
try:
    client = genai.Client()
except Exception:
    st.error("⚠️ Gemini API 클라이언트 초기화에 실패했습니다. Streamlit Cloud 환경인지 확인해 주세요.")
    client = None

st.title("🍽️ 음식과 술 궁합 시각화 대시보드")
st.write("분석 방향을 선택하여, 최고의 궁합을 찾고, 추천받은 항목에 맞는 지역 맛집을 검색해 보세요.")
st.markdown("---")

# ----------------------------------------------------
# 1. 분석 방향 선택 및 차트 데이터 준비
# ----------------------------------------------------

analysis_mode = st.radio(
    "1. 먼저 무엇을 선택하시겠어요?",
    ("음식 먼저 (Food First)", "술 먼저 (Drink First)"),
    index=0,
    horizontal=True
)
st.markdown("---")

best_item_name = None 

if analysis_mode == "음식 먼저 (Food First)":
    st.header("🍴 음식 기반 최고의 술 추천")
    food = st.selectbox("2. 추천을 원하는 대표 음식을 선택하세요:", df["대표음식"].unique())
    row = df[df["대표음식"] == food].iloc[0]
    
    chart_data = []
    for d in DRINKS:
        chart_data.append({
            "항목": f"{EMOJIS_DRINKS.get(d, '❓')} {d}", 
            "비율": row[d],
            "정렬용_비율": row[d],
            "검색어": d 
        })
    chart_df = pd.DataFrame(chart_data).sort_values("정렬용_비율", ascending=False)
    
    x_col = "항목" 
    y_col = "비율"
    main_item = food
    chart_title = f"'{main_item}'과(와) 어울리는 술 비율 🍷"
    best_item = chart_df.iloc[0]["항목"]
    best_item_name = chart_df.iloc[0]["검색어"] # 순수 술 이름

else:
    st.header("🥂 술 기반 최고의 음식 추천")
    selected_drink = st.selectbox("2. 추천을 원하는 술을 선택하세요:", DRINKS)

    recommend_df = df[["대표음식", selected_drink]].sort_values(
        by=selected_drink, ascending=False
    ).head(TOP_N_FOOD)

    chart_df = recommend_df.copy()
    chart_df.columns = ["항목", "비율"] 
    chart_df["정렬용_비율"] = chart_df["비율"]
    chart_df["검색어"] = chart_df["항목"] 

    x_col = "항목" 
    y_col = "비율"
    main_item = selected_drink
    chart_title = f"'{main_item}'과(와) 잘 어울리는 음식 ({TOP_N_FOOD}가지) 🍽️"
    best_item = chart_df.iloc[0]["항목"]
    best_item_name = chart_df.iloc[0]["항목"] # 순수 음식 이름

# ----------------------------------------------------
# 2. 공통 Plotly 시각화 로직
# ----------------------------------------------------

if not chart_df.empty:
    recommendation_type = "술" if analysis_mode == "음식 먼저 (Food First)" else "음식"

    # --- 그래프 출력 ---
    colors = ["#FF4B4B"] + px.colors.sequential.Oranges[2:len(chart_df)]
    colors = colors[:len(chart_df)]

    fig = px.bar(
        chart_df,
        x=x_col, y=y_col, text="비율",
        color="항목", color_discrete_sequence=colors,
        title=chart_title,
        orientation='v' 
    )

    fig.update_traces(texttemplate="%{text:.2f}", textposition="outside")

    fig.update_layout(
        yaxis_range=[0, 1.1], showlegend=False, title_x=0.5,
        plot_bgcolor="rgba(0,0,0,0)", font=dict(size=14),
        xaxis=dict(showgrid=False, title=x_col),
        yaxis=dict(showgrid=False, title="궁합 비율"),
    )

    st.plotly_chart(fig, use_container_width=True)

    # --- 부가 정보 ---
    st.markdown(f"🥇 **'{main_item}'에(는) '{best_item}'가(이) 가장 잘 어울리는 {recommendation_type}입니다!**")
    st.markdown("---")

    # ----------------------------------------------------
    # 3. 지역 맛집 추천 기능 (실제 Gemini API 호출)
    # ----------------------------------------------------
    
    st.header("📍 지역 맛집 추천")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        selected_gu = st.selectbox("3. 서울의 구(區)를 선택하세요:", SEOUL_GUS)
    
    search_query = f"{best_item_name} 맛집 {selected_gu}"
    
    with col2:
        st.markdown(f"<div style='height: 38px;'></div>", unsafe_allow_html=True) 
        search_button = st.button(f"'{search_query}' 검색하기 🔎", use_container_width=True)

    if search_button and client:
        # LLM에게 맛집 정보를 구조화하도록 요청하는 시스템 프롬프트
        system_prompt = (
            "당신은 서울 지역 맛집 전문 큐레이터입니다. "
            "Google 검색 결과를 바탕으로 가장 인기 있는 맛집 1곳을 선정하여, "
            "가게 이름, 대표메뉴, 간단 후기(1줄 이내), 가장 가까운 지하철역 정보를 순서대로 "
            "번호 목록(예: '1. 가게 이름:', '2. 대표메뉴:')으로 정리하여 한국어로 출력하세요. "
            "추가적인 서론이나 결론 문구 없이 오직 목록 형식의 결과만 제공하세요."
        )
        
        with st.spinner(f"**'{search_query}'** 지역 맛집 정보를 검색하고 있습니다..."):
            try:
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=search_query,
                    config=genai.types.GenerateContentConfig(
                        tools=[{"google_search": {}}], # Google 검색 도구 활성화
                        system_instruction=system_prompt
                    )
                )

                # 결과 저장
                st.session_state['matjip_result'] = {
                    "text": response.text,
                    "sources": response.candidates[0].grounding_metadata.grounding_attributions
                }

            except Exception as e:
                st.error(f"맛집 검색 중 오류가 발생했습니다: {e}")
                st.session_state['matjip_result'] = None
    
    if 'matjip_result' in st.session_state and st.session_state['matjip_result'] is not None:
        result = st.session_state['matjip_result']
        
        st.subheader(f"✨ '{search_query}' 추천 결과")

        # 1. LLM이 생성한 구조화된 텍스트 출력
        st.markdown(result["text"])
        
        # 2. 참고 사이트 (Grounding Source) 출력
        sources_html = []
        if result.get("sources"):
            for source in result["sources"]:
                # uri와 title을 사용하여 하이퍼링크 생성
                sources_html.append(f"[{source.web.title}]({source.web.uri})")

            st.markdown(f"**참고 사이트**: {', '.join(sources_html)}")
            
        st.markdown("---")
        st.info("💡 위 정보는 Gemini의 Google 검색 결과를 기반으로 추출된 것입니다. 실제 방문 전 영업 정보와 위치를 꼭 확인하세요.")
