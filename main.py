import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# -------------------------------
# 데이터 불러오기
# -------------------------------
food_df = pd.read_csv("food_data.csv")
drink_df = pd.read_csv("drink_data.csv")

st.set_page_config(page_title="음식-술 궁합 테스트 🍶", page_icon="🍴", layout="centered")

st.title("🍽️ 음식과 술 궁합 테스트")
st.write("데이터 기반으로 계산된 음식과 음료의 조화 점수를 확인해보세요!")

# -------------------------------
# 음식 선택
# -------------------------------
food_choice = st.selectbox("음식을 선택하세요", food_df["food"].unique())
selected_food = food_df[food_df["food"] == food_choice].iloc[0]

st.subheader(f"선택한 음식: **{food_choice}**")
st.write(f"열량: {selected_food.kcal} kcal, 단백질: {selected_food.protein}g, 지방: {selected_food.fat}g, 탄수화물: {selected_food.carbs}g")

# -------------------------------
# 궁합 점수 계산 함수
# -------------------------------
def calculate_pairing(food, drink):
    # 음식 특성 벡터 (탄단지 비율 기반)
    food_vec = np.array([food["protein"], food["fat"], food["carbs"]])
    food_vec = food_vec / np.sum(food_vec)

    # 음료 특성 벡터 (단맛, 산도, 바디감)
    drink_vec = np.array([drink["sweetness"], drink["acidity"], drink["body"]])
    drink_vec = drink_vec / np.max(drink_vec)

    # 유클리드 거리 계산 (가까울수록 조화로움)
    distance = np.linalg.norm(food_vec - drink_vec)
    score = max(0, 100 - distance * 100)  # 0~100점으로 변환
    return round(score, 1)

# -------------------------------
# 계산 및 시각화
# -------------------------------
scores = []
for i, drink in drink_df.iterrows():
    score = calculate_pairing(selected_food, drink)
    scores.append({"음료": drink["drink"], "궁합 점수": score})

result_df = pd.DataFrame(scores).sort_values(by="궁합 점수", ascending=False)

# 상위 추천 출력
top_drink = result_df.iloc[0]
st.markdown(f"### 🥇 가장 잘 어울리는 음료: **{top_drink['음료']} ({top_drink['궁합 점수']}점)**")
st.write("👉 음식의 맛과 영양 프로파일을 기반으로 계산된 결과예요!")

# 그래프 표시
fig = px.bar(result_df, x="음료", y="궁합 점수", color="궁합 점수", range_y=[0, 100])
st.plotly_chart(fig, use_container_width=True)

# 랜덤 조합 버튼
if st.button("🎲 랜덤 음식-술 궁합 보기"):
    random_food = food_df.sample(1).iloc[0]
    random_drink = drink_df.sample(1).iloc[0]
    rand_score = calculate_pairing(random_food, random_drink)
    st.markdown(f"**{random_food['food']} + {random_drink['drink']} = {rand_score}점 🍷**")
