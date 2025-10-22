import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px

# -------------------------------
# 데이터 불러오기
# -------------------------------
food_df = pd.read_csv("food_drink_pairings.csv")

# 음료 데이터 추출
drink_names = food_df["추천술"].unique()
drink_features = pd.DataFrame({
    "drink": drink_names,
    "sweetness": [1,2,3,4,5,3],   # 샘플값, 필요시 수정
    "acidity": [2,3,4,3,2,3],
    "body": [2,1,4,3,5,2]
})

st.set_page_config(page_title="음식-술 궁합 테스트 🍶", page_icon="🍴", layout="centered")
st.title("🍽️ 음식과 술 궁합 테스트")
st.write("데이터 기반으로 계산된 음식과 음료의 조화 점수를 확인해보세요!")

# -------------------------------
# 음식 선택
# -------------------------------
food_choice = st.selectbox("음식을 선택하세요", food_df["음식명"].unique())
selected_food = food_df[food_df["음식명"] == food_choice].iloc[0]

st.subheader(f"선택한 음식: **{food_choice}**")
st.write(f"열량: {selected_food['열량(kcal)']} kcal, 주요 영양성분: {selected_food['주요영양성분']}")

# -------------------------------
# 궁합 점수 계산 함수
# -------------------------------
def calculate_pairing(food, drink):
    # 음식 벡터: 열량 / 임의 스케일링
    food_vec = np.array([food["열량(kcal)"]/1000, 1, 1])  # 임시 값
    # 음료 벡터: sweetness, acidity, body
    drink_vec = np.array([drink["sweetness"]/5, drink["acidity"]/5, drink["body"]/5])
    # 유클리드 거리 → 점수
    distance = np.linalg.norm(food_vec - drink_vec)
    score = max(0, 100 - distance*100)
    return round(score,1)

# -------------------------------
# 점수 계산 및 데이터프레임 생성
# -------------------------------
scores = []
for i, drink in drink_features.iterrows():
    score = calculate_pairing(selected_food, drink)
    scores.append({"음료": drink["drink"], "궁합 점수": score})

result_df = pd.DataFrame(scores).sort_values(by="궁합 점수", ascending=False)

# -------------------------------
# 결과 출력
# -------------------------------
top_drink = result_df.iloc[0]
st.markdown(f"### 🥇 가장 잘 어울리는 음료: **{top_drink['음료']} ({top_drink['궁합 점수']}점)**")
st.write(selected_food["궁합설명"])

# 그래프
fig = px.bar(result_df, x="음료", y="궁합 점수", color="궁합 점수", range_y=[0,100])
st.plotly_chart(fig, use_container_width=True)

# 랜덤 궁합 버튼
if st.button("🎲 랜덤 음식-술 궁합 보기"):
    random_food = food_df.sample(1).iloc[0]
    random_drink = drink_features.sample(1).iloc[0]
    rand_score = calculate_pairing(random_food, random_drink)
    st.markdown(f"**{random_food['음식명']} + {random_drink['drink']} = {rand_score}점 🍷**")

