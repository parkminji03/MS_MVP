import requests, os, json
from openai import AzureOpenAI
from dotenv import load_dotenv


load_dotenv()

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPEN_AI_KEY"),
    api_version= "2024-12-01-preview",
    azure_endpoint=os.getenv("AZURE_OPEN_AI_URL")
)
AZURE_SEARCH_ENDPOINT=os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_INDEX=os.getenv("AZURE_SEARCH_INDEX","survey-responses")

# RAG 응답 
def rag_answer(question,passages, model="gpt-4o-mini"):
    context="\n".join([f"- [{p.get('column')}] ({p.get('sentiment')}): {p.get('text')}" for p in passages])
    prompt=f"""
    당신은 교육 설문 데이터에 기반해 답변해주는 AI입니다.
    아래 컨텍스트(응답)을 참고하여 사용자의 질문에 정확히 답을 해주세요.
    질문에 대한 답을 찾지 못하였으면 찾지 못했다고 대답하세요. 
    거짓말로 답변을 꾸며서 대답하지 마세요.

    컨텍스트:
    {context}

    질문 :
    {question}
    """
    response=client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content":prompt}],
        temperature=0.3
    )
    return response.choices[0].message.content

# 설문응답 csv를 인덱스 문서에 업로드
def index_documents_to_search(docs):
    url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/index?api-version=2024-05-01-preview"
    headers = {"Content-Type": "application/json", "api-key": os.getenv("AZURE_SEARCH_API_KEY")}
    payload = {"value": [{"@search.action": "mergeOrUpload", **doc} for doc in docs]}
    r = requests.post(url, headers=headers, data=json.dumps(payload))
    return r.status_code, r.text

#RAG용 관련 응답 추출
def semantic_search_responses(query, top=8, column_filter=None, sentiment_filter=None):
    url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/search?api-version=2024-05-01-preview"
    headers = {"Content-Type": "application/json", "api-key": os.getenv("AZURE_SEARCH_API_KEY")}
    filter_clauses = []
    if column_filter:
        filter_clauses.append(f"column eq '{column_filter}'")
    if sentiment_filter:
        filter_clauses.append(f"sentiment eq '{sentiment_filter}'")
    filter_expr = " and ".join(filter_clauses) if filter_clauses else None

    payload = {
        "search": query if query.strip() else "*",
        "top": top,
        "queryType": "semantic",   # semantic search 활성화
        "queryLanguage": "ko-kr",
        "semanticConfiguration": "default"  # Portal에서 semantic config 생성 필요
    }
    if filter_expr:
        payload["filter"] = filter_expr

    r = requests.post(url, headers=headers, data=json.dumps(payload))
    if r.status_code != 200:
        return []
    res = r.json()
    hits = res.get("value", [])
    passages = [{"text": h.get("text"), "column": h.get("column"), "sentiment": h.get("sentiment")} for h in hits]
    return passages