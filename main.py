import streamlit as st
import pandas as pd
import plotly.express as px
import json
import base64
from streamlit.components.v1 import html

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
    "소주": "🍶",
    "맥주": "🍺",
    "와인": "🍷",
    "막걸리": "🥛",
    "위스키": "🥃",
    "칵테일": "🍸",
    "사케": "🍶"
}

# --- 데이터 불러오기 ---
@st.cache_data
def load_data():
    """데이터를 불러오고 필요한 술 컬럼 목록을 반환합니다."""
    # 파일명은 사용자 환경에 맞게 조정하세요.
    try:
        df = pd.read_csv("food_drink_pairings.csv")
    except FileNotFoundError:
        st.error("⚠️ food_drink_pairings.csv 파일을 찾을 수 없습니다. 파일을 업로드하거나 경로를 확인하세요.")
        return pd.DataFrame(), []

    drink_cols = [col for col in df.columns if col not in ["음식군", "대표음식"]]
    return df, drink_cols

df, DRINKS = load_data()

st.set_page_config(page_title="🍶 음식 & 술 궁합 대시보드", page_icon="🍽️", layout="centered")

st.title("🍽️ 음식과 술 궁합 시각화 대시보드")
st.write("분석 방향을 선택하여, 최고의 궁합을 찾고, 추천받은 항목에 맞는 지역 맛집을 검색해 보세요.")
st.markdown("---")

# ----------------------------------------------------
# 1. 분석 방향 선택 및 데이터 처리
# ----------------------------------------------------

analysis_mode = st.radio(
    "1. 먼저 무엇을 선택하시겠어요?",
    ("음식 먼저 (Food First)", "술 먼저 (Drink First)"),
    index=0,
    horizontal=True
)
st.markdown("---")

# ----------------------------------------------------
# 2. 로직 분기 및 차트 데이터 준비
# ----------------------------------------------------

best_item_name = None # 최종적으로 추천된 아이템 (검색 키워드로 사용)

if analysis_mode == "음식 먼저 (Food First)":
    st.header("🍴 음식 기반 최고의 술 추천")
    food = st.selectbox("2. 추천을 원하는 대표 음식을 선택하세요:", df["대표음식"].unique())
    row = df[df["대표음식"] == food].iloc[0]
    
    chart_data = []
    for d in DRINKS:
        emoji = EMOJIS_DRINKS.get(d, "❓")
        chart_data.append({
            "항목": f"{emoji} {d}", 
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
        by=selected_drink, 
        ascending=False
    ).head(TOP_N_FOOD)

    chart_df = recommend_df.copy()
    chart_df.columns = ["항목", "비율"] 
    chart_df["정렬용_비율"] = chart_df["비율"]
    chart_df["검색어"] = chart_df["항목"] # 음식 이름이 검색어

    x_col = "항목" 
    y_col = "비율"
    main_item = selected_drink
    chart_title = f"'{main_item}'과(와) 잘 어울리는 음식 ({TOP_N_FOOD}가지) 🍽️"
    best_item = chart_df.iloc[0]["항목"]
    best_item_name = chart_df.iloc[0]["항목"] # 순수 음식 이름

# ----------------------------------------------------
# 3. 공통 Plotly 시각화 로직
# ----------------------------------------------------

if not chart_df.empty:
    recommendation_type = "술" if analysis_mode == "음식 먼저 (Food First)" else "음식"

    # --- 그래프 출력 ---
    with st.container():
        colors = ["#FF4B4B"] + px.colors.sequential.Oranges[2:len(chart_df)]
        colors = colors[:len(chart_df)]

        fig = px.bar(
            chart_df,
            x=x_col, 
            y=y_col, 
            text="비율",
            color="항목", 
            color_discrete_sequence=colors,
            title=chart_title,
            orientation='v' 
        )

        fig.update_traces(
            texttemplate="%{text:.2f}",
            textposition="outside"
        )

        fig.update_layout(
            yaxis_range=[0, 1.1],
            showlegend=False,
            title_x=0.5,
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis=dict(showgrid=False, title=x_col),
            yaxis=dict(showgrid=False, title="궁합 비율"),
            font=dict(size=14)
        )

        st.plotly_chart(fig, use_container_width=True)

    # --- 부가 정보 ---
    st.markdown(f"🥇 **'{main_item}'에(는) '{best_item}'가(이) 가장 잘 어울리는 {recommendation_type}입니다!**")
    st.markdown("---")

    # ----------------------------------------------------
    # 4. 지역 맛집 추천 기능 추가 (Google 검색 시뮬레이션)
    # ----------------------------------------------------
    
    st.header("📍 지역 맛집 추천")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        selected_gu = st.selectbox("3. 서울의 구(區)를 선택하세요:", SEOUL_GUS)
    
    search_query = f"{best_item_name} 맛집 {selected_gu}"
    
    with col2:
        st.markdown(f"<div style='height: 38px;'></div>", unsafe_allow_html=True) 
        search_button = st.button(f"'{search_query}' 검색하기 🔎", use_container_width=True)

    if search_button:
        with st.spinner(f"**'{search_query}'** 지역 맛집 정보를 검색 중입니다..."):
            
            # --- Google Search API 시뮬레이션 ---
            # 실제 API 호출 대신, 검색어에 맞는 가상의 추천 결과를 생성합니다.
            
            # 시뮬레이션 데이터 정의
            simulated_text = f"""
            1. **가게 이름**: {selected_gu}의 {best_item_name} 명가
            2. **대표메뉴**: 최고의 {best_item_name} 요리
            3. **간단 후기**: "궁합 아이템인 '{main_item}'와 함께 먹으니 풍미가 두 배! 재료가 신선하고 맛이 깔끔합니다."
            4. **가장 가까운 지하철역**: {selected_gu}청역 (9호선) 또는 가까운 역 이름
            """
            simulated_sources = [
                {"uri": f"https://www.example.com/matjip/{selected_gu}", "title": f"'{selected_gu} {best_item_name}' 맛집 정보"},
                {"uri": f"https://www.example.com/review/{best_item_name}", "title": f"'{best_item_name}' 추천 후기 블로그"}
            ]

            st.session_state['matjip_result'] = {
                "text": simulated_text,
                "sources": simulated_sources
            }
            # --- 시뮬레이션 끝 ---

    if 'matjip_result' in st.session_state and st.session_state['matjip_result'] is not None:
        result = st.session_state['matjip_result']
        
        st.subheader(f"✨ '{search_query}' 추천 결과")

        # 1. 구조화된 텍스트 출력
        st.markdown(result["text"])
        
        # 2. 참고 사이트 (Grounding Source) 출력
        sources_html = []
        if result.get("sources"):
            for source in result["sources"]:
                if source.get("uri") and source.get("title"):
                    sources_html.append(f"<a href='{source['uri']}' target='_blank'>{source['title']}</a>")

            st.markdown(f"**참고 사이트**: {', '.join(sources_html)}", unsafe_allow_html=True)
            
        st.markdown("---")
        st.info("⚠️ 상기 정보는 Streamlit 환경에서 Google 검색을 시뮬레이션한 결과입니다. 실제 방문 전 영업 정보와 위치를 꼭 확인하세요.")
