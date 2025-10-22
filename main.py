import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

st.set_page_config(page_title="음식-술 궁합 테스트 🍶", page_icon="🍴", layout="centered")
st.title("🍽️ 음식과 술 궁합 테스트")
st.write("음식을 선택하면 가장 잘 어울리는 술과 궁합 점수를 보여드립니다!")

# -------------------------------
# 데이터 불러오기
# -------------------------------
@st.cache_data
def load_data(path: str) -> pd.DataFrame:
    # utf-8-sig 또는 utf-8 모두 허용
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeError:
        return pd.read_csv(path, encoding="utf-8")

food_df = load_data("food_drink_pairings.csv")

# -------------------------------
# 음식열/술열 자동 감지
#  - 케이스1: [대표음식, 소주, 맥주, ...] (스크린샷 형태)
#  - 케이스2: [범주, 음식명, 소주, 맥주, ...] (A열 범주 존재)
# -------------------------------
cols = list(food_df.columns)

def _is_all_numeric(series: pd.Series) -> bool:
    # 90% 이상 숫자면 숫자열로 간주
    s = pd.to_numeric(series, errors="coerce")
    return s.notna().mean() >= 0.9

# 후보 1: 첫 열이 음식명이고 나머지는 숫자(술 점수)
candidate1 = _is_all_numeric(food_df[cols[1]]) if len(cols) > 1 else False
rest_numeric1 = all(_is_all_numeric(food_df[c]) for c in cols[1:]) if len(cols) > 1 else False

# 후보 2: 두 번째 열이 음식명이고, 세 번째 이후가 숫자(술 점수)
rest_numeric2 = all(_is_all_numeric(food_df[c]) for c in cols[2:]) if len(cols) > 2 else False

if len(cols) >= 2 and rest_numeric2:
    # [범주, 음식명, 점수...]
    food_col = cols[1]
    drink_cols = cols[2:]
elif len(cols) >= 2 and rest_numeric1:
    # [음식명, 점수...]
    food_col = cols[0]
    drink_cols = cols[1:]
else:
    # 폴백: 가장 왼쪽 비(준)숫자열을 음식으로, 나머지 숫자열을 술로
    non_numeric_cols = [c for c in cols if not _is_all_numeric(food_df[c])]
    numeric_cols = [c for c in cols if _is_all_numeric(food_df[c])]
    if not non_numeric_cols or not numeric_cols:
        st.error("CSV 열 구조를 파악할 수 없습니다. (왼쪽에 음식명, 오른쪽에 점수들이 오도록 해주세요)")
        st.stop()
    food_col = non_numeric_cols[0]
    drink_cols = numeric_cols

# 점수형으로 강제 변환
for c in drink_cols:
    food_df[c] = pd.to_numeric(food_df[c], errors="coerce")

# -------------------------------
# 스케일 자동 감지 (0~1 → %로 환산)
# -------------------------------
max_val = np.nanmax(food_df[drink_cols].values)
use_percent = (max_val <= 1.0)  # 1.0 이하이면 0~1 스케일로 판단
scale = 100.0 if use_percent else 1.0
y_max = 100.0 if use_percent else float(np.nanmax(food_df[drink_cols].values) * 1.05)

def fmt(v: float) -> str:
    if pd.isna(v):
        return "N/A"
    return f"{v*scale:.2f}" if use_percent else f"{v:.2f}"

# -------------------------------
# 음식 선택
# -------------------------------
food_choice = st.selectbox("음식을 선택하세요", food_df[food_col].dropna().astype(str).unique())

selected_food_row = food_df[food_df[food_col] == food_choice].iloc[0]

# -------------------------------
# 궁합 점수 계산 및 정렬
# -------------------------------
pair_scores = selected_food_row[drink_cols].to_dict()
result_df = pd.DataFrame(list(pair_scores.items()), columns=["음료", "원시점수"])
result_df["점수(표시용)"] = (result_df["원시점수"] * scale).round(2)
result_df = result_df.dropna(subset=["원시점수"]).sort_values(by="원시점수", ascending=False)

# -------------------------------
# 1위 추천
# -------------------------------
top = result_df.iloc[0]
unit = "%" if use_percent else "점"
st.markdown(f"### 🥇 가장 잘 어울리는 음료: **{top['음료']} ({top['점수(표시용)']}{unit})**")

# -------------------------------
# 전체 점수 테이블
# -------------------------------
st.subheader("🍹 전체 술 궁합 점수")
show_df = result_df[["음료", "점수(표시용)"]].reset_index(drop=True)
show_df = show_df.rename(columns={"점수(표시용)": f"궁합 점수 ({unit})"})
st.dataframe(show_df, use_container_width=True)

# -------------------------------
# 막대그래프 + 이모지
# -------------------------------
emoji_map = {
    "소주": "🍶",
    "맥주": "🍺",
    "와인": "🍷",
    "막걸리": "🥛",
    "위스키": "🥃",
    "칵테일": "🍸",
    "사케": "🍶"
}

fig = px.bar(
    result_df,
    x="음료",
    y="점수(표시용)",
    color="점수(표시용)",
    range_y=[0, max(1.0, y_max if use_percent else y_max)],  # 자동 상한
    labels={"점수(표시용)": f"궁합 점수 ({unit})"},
    title=f"🍸 술 궁합 점수 ({unit})"
)

# 이모지 주석 위치 보정 (퍼센트면 +3, 원점수면 전체의 +5%)
offset = 3.0 if use_percent else max(1.0, y_max * 0.05)
for row in result_df.itertuples():
    emoji = emoji_map.get(row.음료, "🍹")
    fig.add_annotation(
        x=row.음료,
        y=row._2 + offset,  # _2는 "점수(표시용)"의 위치 (itertuples 인덱스: 0:Index, 1:음료, 2:원시점수, 3:점수(표시용))
        text=emoji,
        showarrow=False,
        font=dict(size=24),
        xanchor="center"
    )

fig.update_layout(template="plotly_white", height=500)
st.plotly_chart(fig, use_container_width=True)

# -------------------------------
# 랜덤 음식-술 궁합 버튼
# -------------------------------
if st.button("🎲 랜덤 음식-술 궁합 보기"):
    random_food_row = food_df.sample(1).iloc[0]
    random_pair_scores = random_food_row[drink_cols].to_dict()
    rand_df = pd.DataFrame(list(random_pair_scores.items()), columns=["음료", "원시점수"]).dropna()
    rand_df["점수(표시용)"] = (rand_df["원시점수"] * scale).round(2)
    rand_df = rand_df.sort_values(by="원시점수", ascending=False)
    rand_top = rand_df.iloc[0]
    st.markdown(
        f"**{random_food_row[food_col]} + {rand_top['음료']} = {rand_top['점수(표시용)']}{unit} 🍷**"
    )
