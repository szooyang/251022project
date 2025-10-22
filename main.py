import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# ----------------------------------
# 기본 설정
# ----------------------------------
st.set_page_config(page_title="음식-술 궁합 테스트 🍶", page_icon="🍴", layout="centered")
st.title("🍽️ 음식과 술 궁합 테스트")
st.write("음식을 선택하면 가장 잘 어울리는 술과 궁합 점수를 보여드립니다!")

# ----------------------------------
# 유틸
# ----------------------------------
def clean_text_series(s: pd.Series) -> pd.Series:
    """제로폭/NBSP/앞뒤 공백 제거 후 문자열화"""
    return (
        s.astype(str)
         .str.replace("\u200b", "", regex=False)
         .str.replace("\xa0", " ", regex=False)
         .str.strip()
    )

def is_mostly_numeric(series: pd.Series, thresh: float = 0.9) -> bool:
    """값의 90% 이상이 숫자면 숫자열로 간주"""
    s = pd.to_numeric(series, errors="coerce")
    return s.notna().mean() >= thresh

# ----------------------------------
# 데이터 로드
# ----------------------------------
@st.cache_data
def load_csv(path: str) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeError:
        return pd.read_csv(path, encoding="utf-8")

df = load_csv("food_drink_pairings.csv")
if df is None or df.empty:
    st.error("CSV를 불러오지 못했습니다. `food_drink_pairings.csv` 파일을 확인해주세요.")
    st.stop()

cols = list(df.columns)
if len(cols) < 2:
    st.error("CSV에 최소 2개 이상의 열(음식명 + 점수들)이 필요합니다.")
    st.stop()

# ----------------------------------
# 음식열/술열 자동 감지
#  - 케이스1: [음식명, 소주, 맥주, ...]
#  - 케이스2: [범주, 음식명, 소주, 맥주, ...]
# ----------------------------------
# 숫자열 판정
numeric_after_first = all(is_mostly_numeric(df[c]) for c in cols[1:]) if len(cols) > 1 else False
numeric_after_second = all(is_mostly_numeric(df[c]) for c in cols[2:]) if len(cols) > 2 else False

if numeric_after_second:
    # [범주, 음식명, 점수...]
    food_col = cols[1]
    drink_cols = cols[2:]
elif numeric_after_first:
    # [음식명, 점수...]
    food_col = cols[0]
    drink_cols = cols[1:]
else:
    # 폴백: 왼쪽에서 비(준)숫자열 하나 + 오른쪽 숫자열들
    non_numeric = [c for c in cols if not is_mostly_numeric(df[c])]
    numeric = [c for c in cols if is_mostly_numeric(df[c])]
    if not non_numeric or not numeric:
        st.error("CSV 열 구조를 파악할 수 없습니다. 왼쪽에 음식명, 오른쪽에 숫자 점수들이 오도록 정리해주세요.")
        st.stop()
    food_col = non_numeric[0]
    drink_cols = numeric

# 문자열 정규화 컬럼
df["_food_norm"] = clean_text_series(df[food_col])

# 점수형으로 강제 변환
for c in drink_cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")

# 스케일 자동 감지 (0~1 → %로 환산)
max_val = float(np.nanmax(df[drink_cols].values)) if len(drink_cols) else np.nan
use_percent = (max_val <= 1.0)  # 1.0 이하이면 0~1 스케일
scale = 100.0 if use_percent else 1.0
unit = "%" if use_percent else "점"

# ----------------------------------
# UI: 음식 선택
# ----------------------------------
options = df["_food_norm"].dropna().unique()
if len(options) == 0:
    st.error("음식명 열이 비어있습니다. CSV를 확인해주세요.")
    st.stop()

food_choice = st.selectbox("음식을 선택하세요", options)

# 선택 매칭 (안전 가드)
match = df[df["_food_norm"] == food_choice]
if match.empty:
    st.error("선택한 음식명을 찾지 못했습니다. CSV의 음식명에 숨은 문자가 있는지 확인해주세요.")
    st.stop()
selected = match.iloc[0]

# ----------------------------------
# 궁합 계산/정렬
# ----------------------------------
pair_scores = selected[drink_cols].to_dict()
result_df = (
    pd.DataFrame(list(pair_scores.items()), columns=["음료", "원시점수"])
      .dropna(subset=["원시점수"])
      .assign(표시점수=lambda x: (x["원시점수"] * scale).round(2))
      .sort_values("원시점수", ascending=False)
      .reset_index(drop=True)
)

if result_df.empty:
    st.warning("선택한 음식의 점수 데이터가 없습니다.")
    st.stop()

# 1위 추천
top = result_df.iloc[0]
st.markdown(f"### 🥇 가장 잘 어울리는 음료: **{top['음료']} ({top['표시점수']}{unit})**")

# 전체 표
st.subheader("🍹 전체 술 궁합 점수")
st.dataframe(result_df[["음료", "표시점수"]].rename(columns={"표시점수": f"궁합 점수 ({unit})"}), use_container_width=True)

# ----------------------------------
# 시각화
# ----------------------------------
emoji_map = {
    "소주": "🍶", "맥주": "🍺", "와인": "🍷", "막걸리": "🥛",
    "위스키": "🥃", "칵테일": "🍸", "사케": "🍶"
}

ymax_disp = float(result_df["표시점수"].max())
fig = px.bar(
    result_df,
    x="음료",
    y="표시점수",
    color="표시점수",
    range_y=[0, ymax_disp * 1.15 if ymax_disp > 0 else 1],
    labels={"표시점수": f"궁합 점수 ({unit})"},
    title=f"🍸 술 궁합 점수 ({unit})"
)

# 이모지 주석 (퍼센트면 +3, 원점수면 +max*5%)
offset = 3.0 if use_percent else max(1.0, ymax_disp * 0.05)
for row in result_df.itertuples():
    emoji = emoji_map.get(row.음료, "🍹")
    fig.add_annotation(
        x=row.음료,
        y=row.표시점수 + offset,
        text=emoji,
        showarrow=False,
        font=dict(size=24),
        xanchor="center"
    )

fig.update_layout(template="plotly_white", height=520)
st.plotly_chart(fig, use_container_width=True)

# ----------------------------------
# 랜덤 궁합 버튼
# ----------------------------------
if st.button("🎲 랜덤 음식-술 궁합 보기"):
    rand_row = df.sample(1).iloc[0]
    rand_scores = rand_row[drink_cols].to_dict()
    rand_df = (
        pd.DataFrame(list(rand_scores.items()), columns=["음료", "원시점수"])
          .dropna(subset=["원시점수"])
          .assign(표시점수=lambda x: (x["원시점수"] * scale).round(2))
          .sort_values("원시점수", ascending=False)
          .reset_index(drop=True)
    )
    if rand_df.empty:
        st.info("랜덤 선택 결과에 점수 데이터가 없습니다. 다른 항목으로 시도해주세요.")
    else:
        rand_top = rand_df.iloc[0]
        st.markdown(f"**{clean_text_series(pd.Series([rand_row[food_col]])).iloc[0]} + {rand_top['음료']} = {rand_top['표시점수']}{unit} 🍷**")
