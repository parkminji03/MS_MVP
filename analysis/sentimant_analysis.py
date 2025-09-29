import json
import os
from openai import AzureOpenAI
from dotenv import load_dotenv


load_dotenv()

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPEN_AI_KEY"),
    api_version= "2024-12-01-preview",
    azure_endpoint=os.getenv("AZURE_OPEN_AI_URL")
)

#감정분석 AI
def analyze_sentiment(responses,column_name):
    prompt = f"""
    당신은 교육 설문조사를 분석하는 AI 도우미 입니다.
    아래는 "{column_name}" 문항에 대한 학생들의 응답입니다.
    각 응답을 반드시 "긍정", "부정" 중 하나로 분류해주세요
    결과는 JSON 배열로만 반환해주세요.
    - 긍정: 칭찬, 만족, 긍정적인 감정 표현 
    - 부정: 불만, 개선 요구, 부정적인 감정 표현

    

    응답:
    {responses}
    """

    response = client.chat.completions.create(
        model = "gpt-4o-mini",
        messages = [{"role" :"user", "content" : prompt}],
        temperature=0,
        response_format={"type": "json_object"}
    )
    
    content = response.choices[0].message.content
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        print("⚠️ JSON 파싱 실패:", content)
        return []

    # ✅ 다양한 응답 형태를 문자열 리스트로 정규화
    sentiments = []
    if isinstance(parsed, list):
        # ["긍정","부정"] 또는 [{"label":"긍정"}] 형태
        if parsed and isinstance(parsed[0], dict):
            sentiments = [item.get("label") for item in parsed if "label" in item]
        else:
            sentiments = parsed
    elif isinstance(parsed, dict):
        # {"labels": [...]} 형태
        if "labels" in parsed:
            sentiments = parsed["labels"]
        else:
            # dict 값 중 첫 번째 리스트를 사용
            first_val = list(parsed.values())[0]
            sentiments = first_val if isinstance(first_val, list) else [first_val]
    elif isinstance(parsed, str):
        sentiments = [parsed]
    
    positive_keywords = ["재미있게", "좋았", "감사", "유익", "만족", "즐거웠","편안", "잘"]
    negative_keywords = ["불편", "어려웠", "부족", "싫다", "문제", "힘들었", "지저분"]

    def postprocess(response, sentiment):
        if any(kw in response for kw in positive_keywords):
            return "긍정"
        if any(kw in response for kw in negative_keywords):
            return "부정"
        return sentiment

    sentiments = [postprocess(r, s) for r, s in zip(responses, sentiments)]

    return sentiments    


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
def summary_comment(responses, column_name):
    joined = " ".join(responses)
    prompt = f"""
    당신은 교육 설문조사를 요약하는 AI 도우미 입니다.
    아래는 "{column_name}" 문항에 대한 응답들입니다.
    
    - 응답들의 공통된 패턴과 가장 많이 나온 응답을 바탕으로 1줄로 요약하세요.
    - 긍정응답과 부정응답의 주요 특징을 모두 반영하세요.
    - 한국어로 대답하세요.

    응답 :
    {joined}
    """    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )
    return response.choices[0].message.content