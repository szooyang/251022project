import streamlit as st
import pandas as pd
import plotly.express as px

# --- Streamlit 설정 ---
st.set_page_config(page_title="🍶 음식과 술 궁합 시각화", page_icon="🍽️", layout="centered")

# --- 데이터 불러오기 ---
@st.cache_data
def load_data():
    df = pd.read_csv("food_drink_pairings.csv")
    return df

df = load_data()

# --- 이미지 URL (무료 오픈소스 아이콘) ---
icons = {
    "소주": "https://cdn-icons-png.flaticon.com/512/812/812849.png",
    "맥주": "https://cdn-icons-png.flaticon.com/512/2738/2738730.png",
    "와인": "https://cdn-icons-png.flaticon.com/512/3534/3534033.png",
    "막걸리": "https://cdn-icons-png.flaticon.com/512/706/706164.png",
    "위스키": "https://cdn-icons-png.flaticon.com/512/1046/1046751.png",
    "칵테일": "https://cdn-icons-png.flaticon.com/512/861/861210.png",
    "사케": "https://cdn-icons-png.flaticon.com/512/1248/1248795.png"
}

emojis = {
    "소주": "🍶",
    "맥주": "🍺",
    "와인": "🍷",
    "막걸리": "🥛",
    "위스키": "🥃",
    "칵테일": "🍸",
    "사케": "🍶"
}

# --- 제목 ---
st.title("🍽️ 음식과 술 궁합 시각화 대시보드")
st.write("대표 음식을 선택하면, 소주부터 사케까지 각 술과의 궁합 비율을 확인할 수 있습니다.")

# --- 음식 선택 ---
food = st.selectbox("대표 음식을 선택하세요:", df["대표음식"].unique())

# --- 선택한 음식 데이터 필터링 ---
row = df[df["대표음식"] == food].iloc[0]
drinks = ["소주", "맥주", "와인", "막걸리", "위스키", "칵테일", "사케"]

# --- 데이터 구성 ---
chart_df = pd.DataFrame({
    "술": [f"{emojis[d]} {d}" for d in drinks],
    "비율": [row[d] for d in drinks],
    "아이콘": [icons[d] for d in drinks]
}).sort_values("비율", ascending=False)

# --- 색상 설정 ---
colors = ["#FF4B4B"] + px.colors.sequential.Oranges[len(chart_df) - 1:]
colors = colors[:len(chart_df)]

# --- Plotly 그래프 ---
fig = px.bar(
    chart_df,
    x="술",
    y="비율",
    text="비율",
    color="술",
    color_discrete_sequence=colors,
    title=f"'{food}'과(와) 어울리는 술 비율 🍷",
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
    xaxis=dict(showgrid=False),
    yaxis=dict(showgrid=False),
    font=dict(size=16)
)

# --- 그래프 출력 ---
st.plotly_chart(fig, use_container_width=True)

# --- 1등 술 표시 ---
best = chart_df.iloc[0]
st.markdown(f"🥇 **'{food}'에는 {best['술']}이(가) 가장 잘 어울립니다!**")

# --- 이미지 표시 ---
st.subheader("🍸 술 아이콘 보기")
cols = st.columns(len(chart_df))
for i, (_, row_) in enumerate(chart_df.iterrows()):
    with cols[i]:
        st.image(row_["아이콘"], width=60)
        st.caption(row_["술"])

st.markdown("💡 *Tip: 막대 위를 클릭하면 다른 술과 비교하거나 확대해볼 수 있습니다.*")
