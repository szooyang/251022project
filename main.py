import streamlit as st
import pandas as pd
import plotly.express as px

# CSV 파일 불러오기
df = pd.read_csv("food_drink_pairings.csv")

st.set_page_config(page_title="대표 음식별 주류 비율", layout="wide")
st.title("🍽️ 대표 음식별 주류 선호 비율 시각화")

# 술 종류별 이모지 매핑
drink_emojis = {
    "소주": "🍶",
    "맥주": "🍺",
    "와인": "🍷",
    "위스키": "🥃",
    "사케": "🍸",
    "막걸리": "🥛",
}

# 음식 선택
food_list = df["대표음식"].unique()
selected_food = st.selectbox("대표 음식을 선택하세요:", food_list)

# 데이터 필터링
food_data = df[df["음식"] == selected_food].melt(
    id_vars=["음식"], var_name="술 종류", value_name="비율"
)
food_data = food_data.sort_values("비율", ascending=False)

# 이모지 컬럼 추가
food_data["이모지"] = food_data["술 종류"].map(drink_emojis)

# 색상: 1등은 빨간색, 나머지는 Viridis 그라데이션
colors = ["#ff4b4b"] + px.colors.sequential.Viridis[len(food_data) - 1:]

# 그래프 생성
fig = px.bar(
    food_data,
    x="술 종류",
    y="비율",
    text="비율",
    color="술 종류",
    color_discrete_sequence=colors,
)

# 막대 위에 비율 + 이모지 표시
fig.update_traces(
    texttemplate=food_data["이모지"] + " %{text:.1f}%",
    textposition="outside",
    textfont_size=18,
)

# 레이아웃 꾸미기
fig.update_layout(
    title=f"{selected_food}와 어울리는 주류 비율 🍻",
    xaxis_title="주류 종류",
    yaxis_title="비율 (%)",
    showlegend=False,
    plot_bgcolor="rgba(0,0,0,0)",
    paper_bgcolor="rgba(0,0,0,0)",
    title_font_size=24,
)

st.plotly_chart(fig, use_container_width=True)
