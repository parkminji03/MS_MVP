import requests, os, json
from openai import AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AzureOpenAI(
    api_key=os.getenv("AZURE_OPEN_AI_KEY"),
    api_version="2024-12-01-preview",
    azure_endpoint=os.getenv("AZURE_OPEN_AI_URL")
)

AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT")
AZURE_SEARCH_INDEX = os.getenv("AZURE_SEARCH_INDEX", "survey-responses")

# ✅ RAG 응답
def rag_answer(question, passages, model="gpt-4.1-mini"):
    # passages가 dict 리스트인지 보장
    safe_passages = []
    for p in passages:
        if isinstance(p, dict):
            safe_passages.append(p)
        else:
            safe_passages.append({"column": "", "sentiment": "", "text": str(p)})

    context = "\n".join(
        [f"- [{p.get('column','')}] ({p.get('sentiment','')}): {p.get('text','')}" for p in safe_passages]
    )

    prompt = f"""
    당신은 교육 설문 데이터에 기반해 답변해주는 AI입니다.
    아래 컨텍스트(응답)을 참고하여 사용자의 질문에 정확히 답을 해주세요.
    직접적인 답이 없더라도 관련된 내용이 있으면 그에 기반해 추론해서 답변하세요. 
    질문이 길거나 복잡하더라도 핵심 키워드를 뽑아내고, 그 키워드와 관련된 응답을 중심으로 답변하세요.
    근거는 반드시 함께 제시하세요.

    컨텍스트:
    {context}

    질문 :
    {question}
    """

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )
    return response.choices[0].message.content.strip()

# ✅ 설문응답 csv를 인덱스 문서에 업로드
def index_documents_to_search(docs):
    url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/index?api-version=2024-05-01-preview"
    headers = {"Content-Type": "application/json", "api-key": os.getenv("AZURE_SEARCH_API_KEY")}
    all_responses = []

    for i in range(0, len(docs), 10):  # 10개씩 업로드
        batch = docs[i:i+10]
        payload = {"value": [{"@search.action": "mergeOrUpload", **doc} for doc in batch]}
        r = requests.post(url, headers=headers, data=json.dumps(payload))
        all_responses.append((r.status_code, r.text))

        if r.status_code != 200:
            print(f"❌ 인덱싱 실패 (batch {i//10 + 1}):", r.status_code, r.text)
        else:
            print(f"✅ 인덱싱 성공 (batch {i//10 + 1})")

    return all_responses

# 새로운 파일이 업로드 될때마다 index 클리어 
def clear_index():
    url_index = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/index?api-version=2024-05-01-preview"
    url_search = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/search?api-version=2024-05-01-preview"
    headers = {"Content-Type": "application/json", "api-key": os.getenv("AZURE_SEARCH_API_KEY")}

    total_deleted = 0

    while True:
        # 1. 전체 문서 id 조회 (1000개씩)
        r = requests.post(
            url_search,
            headers=headers,
            data=json.dumps({"search": "*", "select": "id", "top": 1000})
        )
        if r.status_code != 200:
            print("❌ 전체 문서 조회 실패:", r.status_code, r.text)
            break

        data = r.json()
        ids = [doc["id"] for doc in data.get("value", []) if "id" in doc]

        if not ids:
            break  # 더 이상 삭제할 문서 없음

        # 2. delete 요청
        payload = {"value": [{"@search.action": "delete", "id": i} for i in ids]}
        r2 = requests.post(url_index, headers=headers, data=json.dumps(payload))

        if r2.status_code == 200:
            total_deleted += len(ids)
            print(f"✅ {len(ids)}개 문서 삭제 완료 (누적 {total_deleted})")
        else:
            print("❌ 삭제 실패:", r2.status_code, r2.text)
            break

    print(f"🔄 인덱스 초기화 완료, 총 {total_deleted}개 문서 삭제됨")

# ✅ 컬럼 후보 자동 추출
def get_available_columns(top=100):
    url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/search?api-version=2024-05-01-preview"
    headers = {"Content-Type": "application/json", "api-key": os.getenv("AZURE_SEARCH_API_KEY")}
    payload = {
        "search": "*",
        "select": "column",
        "top": top
    }
    r = requests.post(url, headers=headers, data=json.dumps(payload))
    if r.status_code == 200:
        data = r.json()
        columns = {doc.get("column") for doc in data.get("value", []) if "column" in doc}
        return list(columns)
    else:
        print("컬럼 추출 실패:", r.status_code, r.text)
        return []

# ✅ 질문 → 컬럼 자동 매핑
def pick_best_columns(question: str, available_columns: list, model="gpt-4.1-mini"):
    prompt = f"""
    당신은 설문 분석 도우미 입니다..
    사용자의 질문이 아래 컬럼 중 어떤 것들과 관련 있는지 모두 골라주세요.
    단어가 정확히 일치하지 않아도 의미적으로 가까운 컬럼을 선택해야 합니다.
    예: 질문에 '교재'라고 하면 '교재평가' 컬럼을 선택해야 해.
    여러 개 선택 가능하며, 없으면 "없음"이라고 답해.

    질문: {question}
    컬럼 후보: {", ".join(available_columns)}
    """
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )
    raw = response.choices[0].message.content.strip()
    if raw == "없음":
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]

# ✅ RAG용 관련 응답 추출 (자동 컬럼 매핑 포함)
def semantic_search_responses(query, top=8, model="gpt-4.1-mini"):
    print("semantic_search_responses 호출됨")
    available_columns = get_available_columns()
    best_columns = [c for c in pick_best_columns(query, available_columns, model=model)
                    if c in available_columns]
    print("📌 질문:", query)
    print("📌 컬럼 후보:", available_columns)
    print("📌 선택된 컬럼:", best_columns)

    url = f"{AZURE_SEARCH_ENDPOINT}/indexes/{AZURE_SEARCH_INDEX}/docs/search?api-version=2024-05-01-preview"
    headers = {"Content-Type": "application/json", "api-key": os.getenv("AZURE_SEARCH_API_KEY")}
    passages = []
    seen = set()

    # 선택된 컬럼이 있으면 각각 검색
    if best_columns:
        for col in best_columns:
            payload = {
                "search": "*",
                "top": top,
                "queryType": "semantic",
                "semanticConfiguration": "default",
                "filter": f"column eq '{col}'",
                "queryLanguage": "ko-KR"
            }
            r = requests.post(url, headers=headers, data=json.dumps(payload))
            if r.status_code == 200:
                data = r.json()
                for doc in data.get("value", []):
                    text = doc.get("text", "")
                    if text not in seen:
                        seen.add(text)
                        passages.append({
                            "column": doc.get("column", ""),
                            "sentiment": doc.get("sentiment", ""),
                            "text": text
                        })
    else:
        # 컬럼 매핑 실패 → 전체 검색 fallback
        print("⚠fallback")
        payload = {"search": query, "top": top, "queryType": "semantic", "semanticConfiguration": "default","queryLanguage": "ko-KR"}
        r = requests.post(url, headers=headers, data=json.dumps(payload))
        if r.status_code == 200:
            data = r.json()
            for doc in data.get("value", []):
                text = doc.get("text", "")
                if text not in seen:
                    seen.add(text)
                    passages.append({
                        "column": doc.get("column", ""),
                        "sentiment": doc.get("sentiment", ""),
                        "text": text
                    })
    print("📌 검색 payload:", payload)
    print("📌 검색 응답:", r.status_code, r.text[:500])
    return passages
