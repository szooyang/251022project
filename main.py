import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# ==============================
# 스트림릿 기본 설정
# ==============================
st.set_page_config(page_title="음식-술 궁합 테스트 🍶", page_icon="🍴", layout="centered")
st.title("🍽️ 음식과 술 궁합 테스트")
st.write("음식을 선택하면 가장 잘 어울리는 술과 궁합 점수를 보여드립니다!")

# ==============================
# 유틸 함수
# ==============================
def clean_text_series(s: pd.Series) -> pd.Series:
    """제로폭/NBSP/앞뒤 공백 제거 후 문자열화"""
    return (
        s.astype(str)
         .str.replace("\u200b", "", regex=False)
         .str.replace("\xa0", " ", regex=False)
         .str.strip()
    )

def mostly_numeric(series: pd.Series, thresh: float = 0.9) -> bool:
    """값의 90% 이상이 숫자면 숫자열로 간주"""
    s = pd.to_numeric(series, errors="coerce")
    return s.notna().mean() >= thresh

def guess_food_and_drinks(df: pd.DataFrame):
    """
    음식열/술열 자동 감지
    우선순위:
      1) 헤더 키워드 매칭 ('대표음식','음식','음식명','Food','Dish' 등)
      2) [범주, 음식명, 점수...] 패턴
      3) [음식명, 점수...] 패턴
      4) 왼쪽에서 가장 텍스트스러우며 유니크 비율이 높은 열
    """
    cols = list(df.columns)

    # 1) 헤더 키워드 우선
    food_keywords = {"대표음식", "음식", "음식명", "메뉴", "Food", "food", "Dish", "dish"}
    header_lower = {c.lower(): c for c in cols}
    for key in list(food_keywords) | {k.lower() for k in food_keywords}:
        if key in header_lower:
            cand = header_lower[key]
            # cand 오른쪽이 대부분 숫자면 이상적
            right_cols = [c for c in cols[cols.index(cand)+1:]]
            if right_cols and all(mostly_numeric(df[c]) for c in right_cols):
                return cand, right_cols

    # 2) [범주, 음식명, 점수...] 패턴
    if len(cols) >= 3:
        if (not mostly_numeric(df[cols[0]])) and (not mostly_numeric(df[cols[1]])) and \
           all(mostly_numeric(df[c]) for c in cols[2:]):
            return cols[1], cols[2:]

    # 3) [음식명, 점수...] 패턴
    if len(cols) >= 2:
        if (not mostly_numeric(df[cols[0]])) and all(mostly_numeric(df[c]) for c in cols[1:]):
            return cols[0], cols[1:]

    # 4) 폴백: 왼쪽에서 텍스트성이 높고 유니크 비율이 높은 열을 음식으로,
    #    그 오른쪽에서 숫자열만 술로 선택
    text_like = []
    for c in cols:
        is_texty = not mostly_numeric(df[c])
        uniq_ratio = df[c].nunique(dropna=True) / max(1, len(df))
        avg_len = clean_text_series(df[c]).str.len().fillna(0).mean()
        text_like.append((c, is_texty, uniq_ratio, avg_len))
    # 텍스트 & 유니크>0.3 & 평균길이>=2 를 우선, 좌->우 정렬
    candidates = [c for (c, is_text, u, L) in text_like if is_text and u >= 0.3 and L >= 2]
    if not candidates:
        # 그래도 없으면 첫 비(준)숫자열
        candidates = [c for (c, is_text, _, _) in text_like if is_text]
    if not candidates:
        raise ValueError("음식명 후보 열을 찾을 수 없습니다.")

    food_col = candidates[0]
    right_cols = [c for c in cols[cols.index(food_col)+1:]]
    drink_cols = [c for c in right_cols if mostly_numeric(df[c])]
    if not drink_cols:
        # 전체에서 숫자열 수집 (최후의 보루)
        drink_cols = [c for c in cols if c != food_col and mostly_numeric(df[c])]
    if not drink_cols:
        raise ValueError("점수(숫자) 열을 찾지 못했습니다.")
    return food_col, drink_cols

# ==============================
# 데이터 로드
# ==============================
@st.cache_data
def load_csv(path: str) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:
            continue
    # 마지막 시도: 인코딩 자동 추정 실패 시 기본 읽기
    return pd.read_csv(path)

df = load_csv("food_drink_pairings.csv")
if df is None or df.empty:
    st.error("CSV를 불러오지 못했습니다. `food_drink_pairings.csv` 파일을 확인해주세요.")
    st.stop()

# 음식/술 열 결정
try:
    food_col, drink_cols = guess_food_and_drinks(df)
except Exception as e:
    st.error(f"CSV 열 구조 판별 중 오류: {e}")
    st.stop()

# 정규화 & 숫자 강제
df["_food_norm"] = clean_text_series(df[food_col])
for c in drink_cols:
    df[c] = pd.to_numeric(df[c], errors="coerce")

# 0~1 스케일이면 %로 변환
max_val = float(np.nanmax(df[drink_cols].values))
use_percent = max_val <= 1.0
scale = 100.0 if use_percent else 1.0
unit = "%" if use_percent else "점"

# ==============================
# UI: 음식 선택 (문자열만)
# ==============================
food_options = df["_food_norm"].dropna().astype(str).unique()
food_options = [x for x in food_options if x != "" and x.lower() != "nan"]

if not food_options:
    st.error("음식명 열이 비어있거나 모두 결측입니다.")
    st.stop()

food_choice = st.selectbox("음식을 선택하세요", food_options)

# 안전 매칭
row = df[df["_food_norm"] == food_choice]
if row.empty:
    st.error("선택한 음식명을 찾지 못했습니다. CSV의 숨은 문자를 확인해주세요.")
    st.stop()
selected = row.iloc[0]

# ==============================
# 궁합 계산/정렬
# ==============================
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

# 표
st.subheader("🍹 전체 술 궁합 점수")
st.dataframe(result_df[["음료", "표시점수"]].rename(columns={"표시점수": f"궁합 점수 ({unit})"}), use_container_width=True)

# ==============================
# 시각화
# ==============================
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

offset = 3.0 if use_percent else max(1.0, ymax_disp * 0.05)
for r in result_df.itertuples():
    fig.add_annotation(
        x=r.음료,
        y=r.표시점수 + offset,
        text=emoji_map.get(r.음료, "🍹"),
        showarrow=False,
        font=dict(size=24),
        xanchor="center"
    )

fig.update_layout(template="plotly_white", height=520)
st.plotly_chart(fig, use_container_width=True)

# ==============================
# 랜덤 버튼
# ==============================
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

# (선택) 디버그: 자동 인식된 열 정보 확인용
with st.expander("🔧 디버그 정보 보기"):
    st.write("선택된 음식명 열:", food_col)
    st.write("선택된 점수(술) 열:", drink_cols)
    st.write("점수 스케일:", "0~1 → % 변환" if use_percent else "원본 점수 사용")
