import json
import os
from openai import AzureOpenAI
from dotenv import load_dotenv
from azure.ai.textanalytics import TextAnalyticsClient
from azure.core.credentials import AzureKeyCredential


load_dotenv()

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPEN_AI_KEY"),
    api_version= "2024-12-01-preview",
    azure_endpoint=os.getenv("AZURE_OPEN_AI_URL")
)

text_client=TextAnalyticsClient(endpoint=os.getenv("AZURE_TEXT_ANALYTICS_ENDPOINT"), credential=AzureKeyCredential(os.getenv("AZURE_TEXT_ANALYTICS_KEY")))

#감정분석 AI
def analyze_sentiment(text_client,texts):
    results=[]
    try:
        # Azure Text Analytics는 최대 10개씩만 허용
        for i in range(0, len(texts), 10):
            batch = texts[i:i+10]
            response = text_client.analyze_sentiment(documents=batch)
            for doc in response:
                if not doc.is_error:
                    label = (doc.sentiment or "").strip().lower()
                    if label == "positive":
                        results.append("긍정")
                    elif label == "negative":
                        results.append("부정")
                    elif label == "neutral":
                        results.append("중립")
                    else:
                        results.append("기타")
                else:
                    results.append("오류")           
    except Exception as e:
        print("Error:", e)
        results.extend(["오류"] * len(texts))
    return results 


#만족도 점수 계산 (5점 만점)
def calculate_satisfaction(sentiments):
    if not sentiments:
        return 0
    
    # dict 형태일 경우 리스트로 변환
    if isinstance(sentiments, dict):
        if "labels" in sentiments:
            sentiments = sentiments["labels"]
        else:
            # dict의 값들을 전부 리스트로 합치기
            sentiments = list(sentiments.values())[0]

    # 리스트가 아닌 경우 문자열 하나일 수도 있음
    if isinstance(sentiments, str):
        sentiments = [sentiments]

    positive = sentiments.count("긍정")
    total = len(sentiments)
    score = (positive / total) * 5 if total > 0 else 0
    return round(score, 2)
    
# 한줄평 
def summary_comment(client,responses, column_name,sentiment_type=None):
    if not responses:
        return f"{column_name} 항목에 {sentiment_type or '응답'} 이 없습니다."
    
    
    joined = " ||".join(responses)
    prompt = f"""
    당신은 교육 설문조사를 요약하는 AI 도우미입니다.
    문항: "{column_name}"

    - 응답들의 공통된 패턴과 자주 나온 의견을 바탕으로 1줄로 요약하세요.
    - 한국어로 대답하세요.

    응답:
    {joined}
    """    
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content

#후처리를 위한 부정 키워드 
NEGATIVE_HINTS = ["너무 빨리", "너무 빨", "불편", "어려웠", "개선", "부족", "문제", "힘들", "아쉽", "불만", "좋겠다", "오탈","오류"]

def adjust_sentiment(text, sentiment):
    for hint in NEGATIVE_HINTS:
        if hint in text:
            return "부정"
    return sentiment

# 컬럼별 분석
def analyze_columns(text_client, client, df, text_columns):
    results = {}
    for col in text_columns:
        responses = df[col].dropna().astype(str).tolist()
        if not responses:
            continue

        sentiments = analyze_sentiment(text_client, responses)
        # ✅ 후처리 규칙 적용 
        sentiments = [adjust_sentiment(r, s) for r, s in zip(responses, sentiments)]
        satisfaction = calculate_satisfaction(sentiments)

        positives = [r for r, s in zip(responses, sentiments) if s == "긍정"]
        negatives = [r for r, s in zip(responses, sentiments) if s == "부정"]

        pos_summary = summary_comment(client, positives, col, sentiment_type="긍정")
        neg_summary = summary_comment(client, negatives, col, sentiment_type="부정")

        results[col] = {
            "responses": responses,
            "sentiments": sentiments,
            "긍정 수": sentiments.count("긍정"),
            "부정 수": sentiments.count("부정"),
            "중립 수": sentiments.count("중립"),
            "만족도 점수": satisfaction,
            "긍정 요약": pos_summary,
            "부정 요약": neg_summary
        }
    return results

# 전체 응답의 만족도 평균
def calculate_overall_score(results):
    all_scores = [info["만족도 점수"] for info in results.values()]
    overall_score = sum(all_scores) / len(all_scores) if all_scores else 0
    return round(overall_score, 2)