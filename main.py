import streamlit as st
import pandas as pd
import plotly.express as px

# -------------------------------
# 데이터 불러오기
# -------------------------------
food_df = pd.read_csv("food_drink_pairings.csv", encoding="utf-8-sig")

# CSV 구조
# A열: 음식 범주 (사용 안함)
# B열: 음식명
# C~I열: 소주, 맥주, 와인, 막걸리, 위스키, 칵테일, 사케

food_col = food_df.columns[1]       # B열: 음식명
drink_cols = food_df.columns[2:]    # C~I열: 술 종류

# -------------------------------
# Streamlit 페이지 설정
# -------------------------------
st.set_page_config(page_title="음식-술 궁합 테스트 🍶", page_icon="🍴", layout="centered")
st.title("🍽️ 음식과 술 궁합 테스트")
st.write("음식을 선택하면 가장 잘 어울리는 술과 궁합 점수를 보여드립니다!")

# -------------------------------
# 음식 선택
# -------------------------------
food_choice = st.selectbox("음식을 선택하세요", food_df[food_col])

# 선택한 음식 행 가져오기
selected_food_row = food_df[food_df[food_col] == food_choice].iloc[0]

# -------------------------------
# 궁합 점수 계산 및 정렬
# -------------------------------
# 음식과 술 점수 조회
pair_scores = selected_food_row[drink_cols].to_dict()

# DataFrame으로 변환
result_df = pd.DataFrame(list(pair_scores.items()), columns=["음료", "궁합 점수"])

# 문자열 → 숫자 변환
result_df["궁합 점수"] = pd.to_numeric(result_df["궁합 점수"], errors="coerce")
result_df.dropna(inplace=True)

# 점수 내림차순 정렬
result_df = result_df.sort_values(by="궁합 점수", ascending=False)

# -------------------------------
# 결과 출력
# -------------------------------
# 1위 추천
top_drink = result_df.iloc[0]
st.markdown(f"### 🥇 가장 잘 어울리는 음료: **{top_drink['음료']} ({top_drink['궁합 점수']}점)**")

# 전체 점수 테이블
st.subheader("🍹 전체 술 궁합 점수")
st.dataframe(result_df.reset_index(drop=True))

# 막대그래프 시각화
fig = px.bar(result_df, x="음료", y="궁합 점수", color="궁합 점수", range_y=[0,100])
st.plotly_chart(fig, use_container_width=True)

# -------------------------------
# 랜덤 음식-술 궁합 버튼
# -------------------------------
if st.button("🎲 랜덤 음식-술 궁합 보기"):
    random_food_row = food_df.sample(1).iloc[0]
    random_pair_scores = random_food_row[drink_cols].to_dict()
    rand_result_df = pd.DataFrame(list(random_pair_scores.items()), columns=["음료", "궁합 점수"])
    rand_result_df["궁합 점수"] = pd.to_numeric(rand_result_df["궁합 점수"], errors="coerce")
    rand_result_df.dropna(inplace=True)
    rand_result_df = rand_result_df.sort_values(by="궁합 점수", ascending=False)
    
    rand_top_drink = rand_result_df.iloc[0]
    st.markdown(f"**{random_food_row[food_col]} + {rand_top_drink['음료']} = {rand_top_drink['궁합 점수']}점 🍷**")
