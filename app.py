import streamlit as st
import pandas as pd
import plotly.express as px 
from plotly.subplots import make_subplots
import plotly.graph_objects as go
import uuid
from analysis.sentimant_analysis import (calculate_overall_score, analyze_columns, 
    client, text_client)
from search.search import index_documents_to_search, semantic_search_responses, rag_answer, clear_index


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
if upload_file:
    try:
        df = pd.read_csv(upload_file)
        if df.empty:
            st.error("❌ 업로드된 CSV 파일이 비어 있습니다.")
        else:
            st.success("업로드 완료 ✅")

            # 기존 인덱스 클리어
            with st.spinner("기존 인덱스를 초기화 중입니다..."):
                clear_index()

            # === 분석 실행 ===
            with st.spinner("설문 데이터를 분석 중입니다..."):
                results = analyze_columns(text_client, client, df, df.columns.tolist())
                overall_score = calculate_overall_score(results)

            # === 인덱싱 ===
            with st.spinner("검색 인덱스를 구축 중입니다..."):
                docs = []
                for col in df.columns:  # CSV의 모든 컬럼을 돌면서
                    responses = results[col]["responses"]
                    sentiments = results[col]["sentiments"]

                    for r, s in zip(responses, sentiments):
                        if str(r).strip():  # 빈 값은 제외
                            docs.append({
                                "id": str(uuid.uuid4()),  # 고유 ID
                                "column": col,            # CSV 컬럼명
                                "sentiment": s,           # 감성분석 결과
                                "text": str(r)            # 응답 텍스트
                            })

                responses = index_documents_to_search(docs)
            # for i, (status, text) in enumerate(responses, start=1):
            #     st.write(f"DEBUG - 인덱싱 응답 (batch {i}):", status, text)

            # === 탭 UI ===
            tabs = st.tabs(["요약", "상세", "QnA"])

            # 요약 탭
            with tabs[0]:
                st.subheader("📝 항목별 요약")
                st.write(f"📊 전체 만족도: {overall_score} / 5점")

                for col, val in results.items():
                    st.markdown(f"**{col}** → 만족도 점수: {val['만족도 점수']} / 5점")
                    st.markdown(f"긍정 요약: {val['긍정 요약']}")
                    st.markdown(f"부정 요약: {val['부정 요약']}")

                    # 컬럼별 긍정/부정 비율
                    sentiments = val["sentiments"]
                    pos_count = sentiments.count("긍정")
                    neg_count = sentiments.count("부정")

                    if pos_count + neg_count > 0:
                        fig_pie = px.pie(
                            names=["긍정", "부정"],
                            values=[pos_count, neg_count],
                            title=f"{col} 응답 비율",
                            color=["긍정", "부정"],
                            color_discrete_map={"긍정": "green", "부정": "red"}
                        )
                        # key 지정해서 중복 에러 방지
                        st.plotly_chart(fig_pie, use_container_width=True, key=f"pie_{col}")
                    else:
                        st.info(f"{col} 항목에는 긍/부정 응답이 없습니다.")   

                # 그래프
                cols = list(results.keys())
                scores = [results[c]["만족도 점수"] for c in cols]
                if cols:
                    fig = px.bar(
                        x=cols,
                        y=scores,
                        labels={'x': '항목', 'y': '만족도 (점수)'},
                        range_y=[0, 5]
                    )
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
                if st.button("검색 실행") and q:
                    with st.spinner("검색 및 답변 생성 중입니다..."):
                        passages = semantic_search_responses(q, top=5, model="gpt-4.1-mini")

                        if passages:
                            # 🤖 RAG 답변 생성
                            answer = rag_answer(q, passages, model="gpt-4.1-mini")

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


