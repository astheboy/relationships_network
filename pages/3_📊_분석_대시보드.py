# pages/3_📊_분석_대시보드.py
import streamlit as st
from supabase import Client, PostgrestAPIResponse
import pandas as pd
import json
import plotly.express as px # 시각화를 위해 Plotly 추가 (pip install plotly)
import os

# --- 페이지 설정 ---
st.set_page_config(page_title="분석 대시보드", page_icon="📊", layout="wide")

# --- Supabase 클라이언트 가져오기 ---
@st.cache_resource
def init_connection():
    url = None
    key = None
    # ... (이전과 동일) ...
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY") # 또는 SUPABASE_ANON_KEY 등 Render에 설정한 이름
        # if url and key:
        #      st.write("DEBUG: Loaded credentials from environment variables") # 디버깅용
        # else:
        #      st.write("DEBUG: Environment variables not found either.") # 디버깅용


    if url and key:
        try:
            return create_client(url, key)
        except Exception as e:
            st.error(f"Supabase 클라이언트 생성 오류: {e}")
            return None
    else:
        # URL 또는 Key를 어디에서도 찾지 못한 경우
        st.error("Supabase 연결 정보(Secrets 또는 환경 변수)를 찾을 수 없습니다.")
        return None

from supabase import create_client
supabase = init_connection()

# --- 인증 확인 ---
if not st.session_state.get('logged_in'):
    st.warning("로그인이 필요합니다.")
    st.stop()

if not supabase:
    st.error("데이터베이스 연결을 확인해주세요.")
    st.stop()

teacher_id = st.session_state.get('teacher_id')
teacher_name = st.session_state.get('teacher_name', '선생님')

st.title(f"📊 {teacher_name}의 분석 대시보드")
st.write("학급과 설문 회차를 선택하여 결과를 분석하고 시각화합니다.")

# --- 학급 및 설문 회차 선택 ---
st.divider()
col1, col2 = st.columns(2)

selected_class_id = None
selected_survey_id = None
selected_class_name = None
selected_survey_name = None

with col1:
    st.subheader("1. 분석 대상 학급 선택")
    try:
        class_response = supabase.table('classes') \
            .select("class_id, class_name") \
            .eq('teacher_id', teacher_id) \
            .order('created_at', desc=False) \
            .execute()

        if class_response.data:
            classes = class_response.data
            class_options = {c['class_name']: c['class_id'] for c in classes}
            class_options_with_prompt = {"-- 학급 선택 --": None}
            class_options_with_prompt.update(class_options) # 맨 앞에 선택 안내 추가
            selected_class_name = st.selectbox(
                "분석할 학급:",
                options=class_options_with_prompt.keys(),
                key="class_select_analysis"
            )
            selected_class_id = class_options_with_prompt.get(selected_class_name)
        else:
            st.info("먼저 '학급 및 학생 관리' 메뉴에서 학급을 생성해주세요.")
    except Exception as e:
        st.error(f"학급 목록 로딩 오류: {e}")

with col2:
    st.subheader("2. 분석 대상 설문 선택")
    if selected_class_id:
        try:
            survey_response = supabase.table('surveys') \
                .select("survey_instance_id, survey_name") \
                .eq('class_id', selected_class_id) \
                .order('created_at', desc=True) \
                .execute()

            if survey_response.data:
                surveys = survey_response.data
                survey_options = {s['survey_name']: s['survey_instance_id'] for s in surveys}
                survey_options_with_prompt = {"-- 설문 선택 --": None}
                survey_options_with_prompt.update(survey_options)
                selected_survey_name = st.selectbox(
                    f"'{selected_class_name}' 학급의 설문:",
                    options=survey_options_with_prompt.keys(),
                    key="survey_select_analysis"
                )
                selected_survey_id = survey_options_with_prompt.get(selected_survey_name)
            else:
                st.info("선택된 학급에 대한 설문이 없습니다. '설문 관리' 메뉴에서 생성해주세요.")
        except Exception as e:
            st.error(f"설문 목록 로딩 오류: {e}")
    else:
        st.info("먼저 학급을 선택해주세요.")

# --- 데이터 로드 및 분석 ---
st.divider()
if selected_class_id and selected_survey_id:
    st.subheader(f"'{selected_class_name}' - '{selected_survey_name}' 분석 결과")

    @st.cache_data(ttl=300) # 5분 캐싱
    def load_analysis_data(_survey_instance_id):
        try:
            # 1. 응답 데이터 로드 (학생 정보 포함)
            response = supabase.table('survey_responses') \
                .select("*, students(student_id, student_name)") \
                .eq('survey_instance_id', _survey_instance_id) \
                .execute()

            if not response.data:
                st.warning("선택된 설문에 대한 응답 데이터가 없습니다.")
                return None, None

            responses_df = pd.DataFrame(response.data)

            # 2. 학생 이름 매핑 및 'relation_mapping_data' 파싱
            all_students_map = {} # 전체 학생 ID:이름 맵
            parsed_responses = []

            for index, row in responses_df.iterrows():
                student_info = row.get('students') # students(student_id, student_name) 부분
                if not student_info: continue # 학생 정보 없으면 건너뛰기

                submitter_id = student_info['student_id']
                submitter_name = student_info['student_name']
                all_students_map[submitter_id] = submitter_name # 학생 맵에 추가

                # JSON 파싱
                relation_data = {}
                try:
                    if row.get('relation_mapping_data'):
                        relation_data = json.loads(row['relation_mapping_data'])
                except json.JSONDecodeError:
                    print(f"Warning: Failed to parse relation_mapping_data for response {row.get('response_id')}")

                # 파싱된 데이터와 함께 저장
                parsed_row = row.to_dict()
                parsed_row['submitter_id'] = submitter_id
                parsed_row['submitter_name'] = submitter_name
                parsed_row['parsed_relations'] = relation_data # 파싱된 dict 저장
                parsed_responses.append(parsed_row)

            if not parsed_responses:
                 st.warning("유효한 응답 데이터 처리 중 문제가 발생했습니다.")
                 return None, None

            analysis_df = pd.DataFrame(parsed_responses)
            return analysis_df, all_students_map

        except Exception as e:
            st.error(f"분석 데이터 로드 중 오류 발생: {e}")
            return None, None

    # 데이터 로드 실행
    analysis_df, students_map = load_analysis_data(selected_survey_id)

    if analysis_df is not None and students_map:
        # --- 탭 구성 (기본 분석 + AI 분석 탭) ---
        tab_list = ["📊 관계 분석", "💬 서술형 응답", "📄 원본 데이터", "✨ AI 심층 분석"]
        tab1, tab2, tab3, tab4 = st.tabs(tab_list)

        with tab1:
            st.header("관계 분석 (친밀도 점수 기반)")
            # --- !!! 여기에 기본적인 관계 점수 분석 및 시각화 코드 !!! ---
            # (예: 평균 받은 점수 막대 그래프 등 이전 단계에서 구현한 내용)
                        # 1. 받은 친밀도 점수 계산
            received_scores = {} # key: student_id, value: list of scores received
            for student_id in students_map.keys():
                received_scores[student_id] = []

            for index, row in analysis_df.iterrows():
                relations = row.get('parsed_relations', {})
                for target_student_id, relation_info in relations.items():
                    score = relation_info.get('intimacy')
                    if isinstance(score, (int, float)) and target_student_id in received_scores:
                        received_scores[target_student_id].append(score)

            # 2. 평균 받은 점수 계산 및 시각화
            avg_received_scores = []
            for student_id, scores in received_scores.items():
                if scores:
                    avg_score = sum(scores) / len(scores)
                    avg_received_scores.append({
                        'student_id': student_id,
                        'student_name': students_map.get(student_id, 'Unknown'),
                        'average_score': avg_score,
                        'received_count': len(scores)
                    })

            if avg_received_scores:
                avg_df = pd.DataFrame(avg_received_scores).sort_values(by='average_score', ascending=False)

                st.subheader("학생별 평균 받은 친밀도 점수")
                fig = px.bar(avg_df, x='student_name', y='average_score',
                             title="평균 받은 친밀도 점수 (높을수록 긍정적 관계)",
                             labels={'student_name':'학생 이름', 'average_score':'평균 점수'},
                             hover_data=['received_count'], # 마우스 올리면 받은 횟수 표시
                             color='average_score', # 점수에 따라 색상 변화
                             color_continuous_scale=px.colors.sequential.Viridis) # 색상 스케일
                st.plotly_chart(fig, use_container_width=True)

                # 간단 분석
                highest = avg_df.iloc[0]
                lowest = avg_df.iloc[-1]
                st.write(f"🌟 가장 높은 평균 점수를 받은 학생: **{highest['student_name']}** ({highest['average_score']:.1f}점, {highest['received_count']}회)")
                st.write(f"😟 가장 낮은 평균 점수를 받은 학생: **{lowest['student_name']}** ({lowest['average_score']:.1f}점, {lowest['received_count']}회)")
            else:
                st.write("받은 친밀도 점수 데이터가 부족하여 분석할 수 없습니다.")
            st.write("기본 관계 분석 내용 표시")

        with tab2:
            st.header("서술형 응답 보기")
            # --- !!! 여기에 서술형 응답 DataFrame 표시 코드 !!! ---
            text_columns = [
                'submitter_name', 'praise_friend', 'praise_reason', 'difficult_friend',
                'difficult_reason', 'otherclass_friendly_name', 'otherclass_friendly_reason',
                'otherclass_bad_name', 'otherclass_bad_reason', 'concern', 'teacher_message'
            ]
            # analysis_df에 해당 컬럼들이 있는지 확인 후 선택
            available_text_columns = [col for col in text_columns if col in analysis_df.columns]
            st.dataframe(analysis_df[available_text_columns], use_container_width=True)
            st.write("서술형 응답 테이블 표시")
            # text_columns = [...]
            # st.dataframe(analysis_df[available_text_columns])

        with tab3:
            st.header("원본 데이터 보기")
            # --- !!! 여기에 전체 원본 DataFrame 표시 코드 !!! ---
            st.dataframe(analysis_df, use_container_width=True)
            st.caption("`parsed_relations` 열에서 각 학생이 다른 학생들에게 매긴 친밀도 점수를 확인할 수 있습니다.")
            st.write("원본 데이터 테이블 표시")
            # st.dataframe(analysis_df)

        # --- AI 심층 분석 탭 (조건부 내용 표시) ---
        with tab4:
            st.header("AI 기반 심층 분석 (Gemini)")

            # 세션에서 API 키 확인
            api_key = st.session_state.get('gemini_api_key')

            if api_key:
                st.success("✅ Gemini API 키가 활성화되어 AI 분석 기능을 사용할 수 있습니다.")
                st.write("AI 분석 결과를 여기에 표시합니다. (예: 주요 고민 요약, 관계 패턴 분석 등)")

                # --- !!! 여기에 AI 분석 실행 버튼 및 결과 표시 로직 구현 !!! ---
                # 예시:
                if st.button("학생 고민 내용 AI 요약"):
                    # analysis_df['concern'] 내용을 가져와서 Gemini API 호출
                    # 결과 표시
                    st.info("AI 요약 기능 구현 예정")
                    pass

                # 다른 AI 분석 기능 추가...

            else:
                # API 키가 없을 때 안내 메시지 및 설정 페이지 링크 표시
                st.warning("⚠️ AI 기반 분석 기능을 사용하려면 Gemini API 키가 필요합니다.")
                st.markdown("""
                    API 키를 입력하면 학생들의 서술형 응답에 대한 자동 요약, 주요 키워드 추출,
                    관계 패턴에 대한 심층적인 해석 등 추가적인 분석 결과를 얻을 수 있습니다.

                    API 키는 **왼쪽 사이드바의 '⚙️ 설정' 메뉴**에서 입력할 수 있습니다.
                    키 발급은 [Google AI Studio](https://aistudio.google.com/app/apikey)에서 가능합니다.
                """)
                # 설정 페이지로 바로 이동하는 링크 (선택 사항)
                st.page_link("pages/4_⚙️_설정.py", label="설정 페이지로 이동하여 API 키 입력하기", icon="⚙️")

    else:
        # 데이터 로드 실패 시 (load_analysis_data 함수 내에서 이미 경고/오류 표시됨)
        pass

else:
    st.info("분석할 학급과 설문을 선택해주세요.")