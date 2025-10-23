import streamlit as st
import pandas as pd
import plotly.express as px

# --- 설정값 ---
TOP_N_FOOD = 10 # 술을 선택했을 때 추천할 음식 개수
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

    # '음식군'과 '대표음식'을 제외한 나머지 컬럼이 술 종류라고 가정합니다.
    drink_cols = [col for col in df.columns if col not in ["음식군", "대표음식"]]
    return df, drink_cols

df, DRINKS = load_data()

st.set_page_config(page_title="🍶 음식 & 술 궁합 대시보드", page_icon="🍽️", layout="centered")

st.title("🍽️ 음식과 술 궁합 시각화 대시보드")
st.write("분석 방향을 선택하여, 음식에 대한 최고의 술 조합 또는 술에 대한 최고의 음식 조합을 확인하세요.")
st.markdown("---")

# ----------------------------------------------------
# 1. 분석 방향 선택
# ----------------------------------------------------
analysis_mode = st.radio(
    "1. 먼저 무엇을 선택하시겠어요?",
    ("음식 먼저 (Food First)", "술 먼저 (Drink First)"),
    index=0,
    horizontal=True
)
st.markdown("---")

# ----------------------------------------------------
# 2. 선택에 따른 입력 위젯 및 시각화 로직 분기
# ----------------------------------------------------

if analysis_mode == "음식 먼저 (Food First)":
    # ----------------------------------------------------
    # A. '음식 먼저' 모드 (기존 로직: 음식 -> 술, 세로 막대)
    # ----------------------------------------------------
    st.header("🍴 음식 기반 최고의 술 추천")

    # --- 음식 선택 ---
    food = st.selectbox("2. 추천을 원하는 대표 음식을 선택하세요:", df["대표음식"].unique())

    # --- 선택한 음식 데이터 필터링 ---
    row = df[df["대표음식"] == food].iloc[0]

    # --- 이모지와 함께 데이터 구성 ---
    chart_data = []
    for d in DRINKS:
        emoji = EMOJIS_DRINKS.get(d, "❓")
        chart_data.append({
            "항목": f"{emoji} {d}", # Y축 항목 (술)
            "비율": row[d],
            "정렬용_비율": row[d] 
        })
        
    chart_df = pd.DataFrame(chart_data).sort_values("정렬용_비율", ascending=False)
    
    # 차트 변수 설정
    x_col = "항목" 
    y_col = "비율"
    main_item = food
    chart_title = f"'{main_item}'과(와) 어울리는 술 비율 🍷"
    best_item = chart_df.iloc[0]["항목"]
    
else:
    # ----------------------------------------------------
    # B. '술 먼저' 모드 (수정된 로직: 술 -> 음식, 세로 막대)
    # ----------------------------------------------------
    st.header("🥂 술 기반 최고의 음식 추천")

    # --- 술 선택 ---
    selected_drink = st.selectbox("2. 추천을 원하는 술을 선택하세요:", DRINKS)

    # --- 데이터 처리 및 정렬 ---
    recommend_df = df[["대표음식", selected_drink]].sort_values(
        by=selected_drink, 
        ascending=False
    ).head(TOP_N_FOOD)

    # 차트 구성을 위한 DataFrame 이름 통일 (세로 막대를 위해)
    chart_df = recommend_df.copy()
    chart_df.columns = ["항목", "비율"] # X축 항목 (대표음식)
    chart_df["정렬용_비율"] = chart_df["비율"] 
    
    # 차트 변수 설정
    x_col = "항목" 
    y_col = "비율"
    main_item = selected_drink
    chart_title = f"'{main_item}'과(와) 잘 어울리는 음식 ({TOP_N_FOOD}가지) 🍽️"
    best_item = chart_df.iloc[0]["항목"] # '항목' 컬럼에 현재는 '대표음식' 이름이 들어있음

# ----------------------------------------------------
# 3. 공통 Plotly 시각화 로직 (항상 세로 막대)
# ----------------------------------------------------

if not chart_df.empty:
    # --- 색상 설정 (1등 빨강 + 그라데이션) ---
    # 비율이 가장 높은 막대만 빨간색(#FF4B4B)으로 설정
    colors = ["#FF4B4B"] + px.colors.sequential.Oranges[2:len(chart_df)]
    colors = colors[:len(chart_df)]

    # Plotly 막대그래프 생성 (세로 막대: orientation='v')
    fig = px.bar(
        chart_df,
        x=x_col, # 술(Food First) 또는 음식(Drink First)
        y=y_col, # 비율
        text="비율",
        color="항목", # 항목별로 다른 색상 적용
        color_discrete_sequence=colors,
        title=chart_title,
        orientation='v' 
    )

    fig.update_traces(
        texttemplate="%{text:.2f}",
        textposition="outside"
    )

    # 레이아웃 설정 (세로 막대 공통)
    fig.update_layout(
        yaxis_range=[0, 1.1],
        showlegend=False,
        title_x=0.5,
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(showgrid=False, title=x_col),
        yaxis=dict(showgrid=False, title="궁합 비율"),
        font=dict(size=14)
    )

    # --- 그래프 출력 ---
    st.plotly_chart(fig, use_container_width=True)

    # --- 부가 정보 ---
    recommendation_type = "술" if analysis_mode == "음식 먼저 (Food First)" else "음식"
    st.markdown(f"🥇 **'{main_item}'에(는) '{best_item}'가(이) 가장 잘 어울리는 {recommendation_type}입니다!**")
    st.markdown("💡 *Tip: 막대 위를 클릭하면 다른 항목과 비교하거나 확대해볼 수 있습니다.*")
