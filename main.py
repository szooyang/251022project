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
    # A. '음식 먼저' 모드 (기존 로직)
    # ----------------------------------------------------
    st.header("🍴 음식 기반 최고의 술 추천")

    # --- 음식 선택 ---
    food = st.selectbox("2. 추천을 원하는 대표 음식을 선택하세요:", df["대표음식"].unique())

    # --- 선택한 음식 데이터 필터링 ---
    # .iloc[0]로 한 행(Series)을 가져옴
    row = df[df["대표음식"] == food].iloc[0]

    # --- 이모지와 함께 데이터 구성 ---
    chart_data = []
    for d in DRINKS:
        # 이모지를 딕셔너리에서 찾아 적용
        emoji = EMOJIS_DRINKS.get(d, "❓")
        chart_data.append({
            "술": f"{emoji} {d}",
            "비율": row[d],
            "정렬용_비율": row[d] # 정렬을 위해 순수 비율을 따로 저장
        })
        
    chart_df = pd.DataFrame(chart_data).sort_values("정렬용_비율", ascending=False)
    
    y_col = "비율"
    x_col = "술"
    main_item = food
    chart_title = f"'{main_item}'과(와) 어울리는 술 비율 🍷"
    best_item = chart_df.iloc[0]["술"]
    
else:
    # ----------------------------------------------------
    # B. '술 먼저' 모드 (새로운 로직)
    # ----------------------------------------------------
    st.header("🥂 술 기반 최고의 음식 추천")

    # --- 술 선택 ---
    selected_drink = st.selectbox("2. 추천을 원하는 술을 선택하세요:", DRINKS)

    # --- 데이터 처리 및 정렬 ---
    recommend_df = df[["대표음식", selected_drink]].sort_values(
        by=selected_drink, 
        ascending=False
    ).head(TOP_N_FOOD)

    # 차트 구성을 위한 DataFrame 이름 통일
    chart_df = recommend_df.copy()
    chart_df.columns = ["술", "비율"] # '대표음식'을 '술' 컬럼으로 임시 변경하여 통합 차트 로직에 맞춤
    chart_df["정렬용_비율"] = chart_df["비율"] # 정렬용 비율 컬럼 추가
    
    y_col = "술" # 가로 막대를 위해 축 전환
    x_col = "비율"
    main_item = selected_drink
    chart_title = f"'{main_item}'과(와) 잘 어울리는 음식 ({TOP_N_FOOD}가지) 🍽️"
    best_item = chart_df.iloc[0]["술"] # '술' 컬럼에 현재는 '대표음식' 이름이 들어있음

# ----------------------------------------------------
# 3. 공통 Plotly 시각화 로직
# ----------------------------------------------------

if not chart_df.empty:
    # --- 색상 설정 (1등 빨강 + 그라데이션) ---
    # 가장 높은 비율의 막대만 빨간색(#FF4B4B)으로 설정
    colors = ["#FF4B4B"] + px.colors.sequential.Oranges[2:len(chart_df)]
    colors = colors[:len(chart_df)]

    # Plotly 막대그래프 생성
    fig = px.bar(
        chart_df,
        x=x_col,
        y=y_col,
        text="비율",
        color=y_col if analysis_mode == "음식 먼저 (Food First)" else x_col, # 색상 구분을 술 또는 음식 이름으로
        color_discrete_sequence=colors,
        title=chart_title,
        orientation='v' if analysis_mode == "음식 먼저 (Food First)" else 'h' # 분석 모드에 따라 가로/세로 변경
    )

    fig.update_traces(
        texttemplate="%{text:.2f}",
        textposition="outside"
    )

    # 레이아웃 설정
    layout_settings = {
        "showlegend": False,
        "title_x": 0.5,
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": dict(size=14)
    }

    if analysis_mode == "음식 먼저 (Food First)":
        # 세로 막대 설정
        layout_settings["yaxis_range"] = [0, 1.1]
        layout_settings["xaxis"] = dict(showgrid=False)
        layout_settings["yaxis"] = dict(showgrid=False, title="궁합 비율")
        fig.update_layout(**layout_settings)
    else:
        # 가로 막대 설정
        layout_settings["xaxis_range"] = [0, 1.1]
        layout_settings["xaxis"] = dict(showgrid=False, title="궁합 비율")
        layout_settings["yaxis"] = dict(showgrid=False, title="추천 음식", autorange="reversed")
        fig.update_layout(**layout_settings)

    # --- 그래프 출력 ---
    st.plotly_chart(fig, use_container_width=True)

    # --- 부가 정보 ---
    recommendation_type = "술" if analysis_mode == "음식 먼저 (Food First)" else "음식"
    st.markdown(f"🥇 **'{main_item}'에(는) '{best_item}'가(이) 가장 잘 어울리는 {recommendation_type}입니다!**")
    st.markdown("💡 *Tip: 막대 위를 클릭하면 다른 항목과 비교하거나 확대해볼 수 있습니다.*")
