# AI 기반 교육 설문조사 분석 서비스
AI 텍스트 감정분석 및 요약하여 교육에 대한 만족도를 수치화 및 시각화를 해주는 서비스

## 필수 라이브러리 설치 
``` C
# 패키지 설치
pip install -r requirements.txt

#추가 패키지 설치
pip install streamlit transformers torch plotly dotenv azure-ai-textanalytics
```
## .env 파일 설정
``` C
AZURE_OPEN_AI_KEY=<openai apikey>
AZURE_OPEN_AI_URL=<OPENAI endpoint>

AZURE_SEARCH_ENDPOINT=<ai search endpoint>
AZURE_SEARCH_API_KEY=<ai api key>
AZURE_SEARCH_INDEX=survey-responses

AZURE_TEXT_ANALYTICS_ENDPOINT=<language service endpoint>
AZURE_TEXT_ANALYTICS_KEY=<language service key>
```


