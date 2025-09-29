import streamlit as st
import pandas as pd
import plotly.express as px 
import uuid
from analysis.sentimant_analysis import analyze_sentiment, summary_comment, calculate_satisfaction
from search.search import index_documents_to_search, semantic_search_responses, rag_answer
#streamlit UI 

# 페이지 설정
st.set_page_config(
    page_title="교육 설문조사 AI 분석기",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 교육 설문조사 분석 및 QnA")
st.write("설문조사 CSV 파일을 업로드하면 자동으로 분석합니다.")

#파일 업로드
upload_file = st.file_uploader("설문조사 CSV 파일 업로드", type=["csv"])
if upload_file is not None:
    try:
        df = pd.read_csv(upload_file)
        if df.empty:
            st.error("❌ 업로드된 CSV 파일이 비어 있습니다.")
        else:
            st.success("업로드 완료 ✅")

            # -------------------------------
            # 감정분석 + 요약 + 만족도 계산
            # -------------------------------
            results = {}
            for column in df.columns:
                responses = df[column].dropna().astype(str).tolist()
                if not responses:
                    continue

                sentiments = analyze_sentiment(responses, column)
                # # 🔎 디버깅 로그: 실제 감정분석 결과 찍기
                # st.write(f"DEBUG - {column} 감정분석 결과:", sentiments)

                positives = [r for r, s in zip(responses, sentiments) if s == "긍정"]
                summary = summary_comment(positives, column)
                satisfaction = calculate_satisfaction(sentiments)

                results[column] = {
                    "responses": responses,
                    "sentiments": sentiments,
                    "summary": summary,
                    "satisfaction": satisfaction
                }

            # -------------------------------
            # 업로드 직후 자동 인덱싱 (덮어쓰기 아님)
            # -------------------------------
            docs = []
            for col in results.keys():
                for r, s in zip(results[col]["responses"], results[col]["sentiments"]):
                    docs.append({
                        "id": str(uuid.uuid4()),
                        "column": col,
                        "sentiment": s,
                        "text": r
                    })
            status, text = index_documents_to_search(docs)
            # st.write("DEBUG - 인덱싱 응답:", status, text)

            if status == 200:
                st.info("📤 업로드와 동시에 인덱싱 완료!")
            else:
                st.error(f"인덱싱 실패: {status} {text}")

            # -------------------------------
            # 탭 UI (요약 / 상세 / QnA)
            # -------------------------------
            tabs = st.tabs(["요약", "상세", "QnA"])

            # 요약 탭
            with tabs[0]:
                st.subheader("📝 항목별 요약")
                for col, val in results.items():
                    st.markdown(f"**{col}** → {val['summary']} (만족도: {val['satisfaction']} / 5점)")

                # 만족도 그래프
                cols = list(results.keys())
                scores = [results[c]["satisfaction"] for c in cols]
                if cols:
                    fig = px.bar(x=cols, y=scores,
                                 labels={'x': '항목', 'y': '만족도 (점수)'},
                                 range_y=[0, 5])
                    st.plotly_chart(fig, use_container_width=True)

            # 상세 탭
            with tabs[1]:
                st.subheader("📋 항목별 상세 응답")
                col = st.selectbox("항목 선택", list(results.keys()))
                pos = [r for r, s in zip(results[col]["responses"], results[col]["sentiments"]) if s == "긍정"]
                neg = [r for r, s in zip(results[col]["responses"], results[col]["sentiments"]) if s == "부정"]

                col1, col2 = st.columns(2)

                with col1:
                    st.markdown("✅ **긍정 응답**")
                    if pos:
                        for r in pos:
                            st.success(r)
                    else:
                        st.info("긍정 응답 없음")

                with col2:
                    st.markdown("❌ **부정 응답**")
                    if neg:
                        for r in neg:
                            st.error(r)
                    else:
                        st.info("부정 응답 없음")

            # QnA 탭
            with tabs[2]:
                st.subheader("💬 Semantic QnA")
                q = st.text_input("질문 입력")
                if st.button("검색 실행"):
                    passages = semantic_search_responses(q, top=5)

                    # 🔎 디버깅 로그: 검색 결과 찍기
                    st.write("DEBUG - 검색 결과:", passages)

                    if passages:
                        answer = rag_answer(q, passages)
                        st.markdown("**답변:**")
                        st.write(answer)
                        st.markdown("**근거:**")
                        for p in passages:
                            st.caption(f"[{p['column']}] ({p['sentiment']}) {p['text']}")
                    else:
                        st.warning("검색결과 없음")

    except Exception as e:
        st.error(f"❌ 파일 처리 중 오류 발생: {e}")

else:
    st.info("⬆️ CSV 파일을 업로드해주세요.")


