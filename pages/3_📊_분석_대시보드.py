# pages/3_📊_분석_대시보드.py
import streamlit as st
from supabase import Client, PostgrestAPIResponse
import pandas as pd
import json
import plotly.express as px # 시각화를 위해 Plotly 추가 (pip install plotly)
import os
from utils import call_gemini
import itertools
from fpdf import FPDF        # PDF 생성을 위해 추가
from io import BytesIO      # 메모리 버퍼 사용 위해 추가
import datetime
import traceback
import hashlib   

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

def create_pdf(text_content, title="AI 분석 결과"):
    pdf = FPDF()
    pdf.add_page()

    # 한글 폰트 추가
    try:
        font_path = 'fonts/NanumGothicCoding.ttf'
        pdf.add_font('NanumGothic', '', font_path, uni=True)
        pdf.set_font('NanumGothic', size=16)
    except Exception as e:
        st.error(f"PDF 오류: 폰트 처리 중 오류 - {e}")
        return None

    # 제목
    try:
        pdf.cell(0, 10, txt=title, ln=1, align='C')
        pdf.ln(10)
    except Exception as e:
        st.error(f"PDF 제목 쓰기 오류: {e}")
        return None

    # 본문
    pdf.set_font('NanumGothic', size=10)
    try:
        pdf.multi_cell(0, 5, txt=text_content)
    except Exception as e:
        st.error(f"PDF 내용 쓰기 오류: {e}")
        return None

    # PDF 데이터를 바이트 형태로 반환 (수정된 부분 - 타입 체크 완화)
    try:
        pdf_data = pdf.output() # 바이트 또는 바이트 배열 반환 기대

        # 반환값이 bytes 또는 bytearray 인지 확인 (더 유연하게)
        if isinstance(pdf_data, (bytes, bytearray)):
             return pdf_data # 그대로 반환
        else:
             # 예상치 못한 타입 반환 시 오류 발생
             raise TypeError(f"pdf.output() did not return bytes or bytearray (returned {type(pdf_data)}).")

    except Exception as e_output:
        st.error(f"PDF 데이터 생성(출력) 중 오류: {e_output}")
        print("PDF Output Error Traceback:")
        traceback.print_exc()
        return None

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
        tab_list = ["📊 관계 분석", "💬 서술형 응답", "✨ AI 심층 분석"]
        tab1, tab2, tab3 = st.tabs(tab_list)

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
            st.divider() # 구분선 추가

            # --- 2. 준 친밀도 점수 분석 (새로 추가) ---
            st.subheader("학생별 평균 준 친밀도 점수")

            # 함수: 각 학생이 '준' 점수들의 평균과 목록 계산
            @st.cache_data # 계산 결과를 캐싱하여 성능 향상
            def calculate_given_scores(df, student_map, id_col='submitter_id', name_col='submitter_name', relations_col='parsed_relations'):
                given_scores_list = []
                # submitter_id 기준으로 순회 (한 학생당 한 번만 계산)
                for submitter_id, group in df.groupby(id_col):
                    submitter_name = student_map.get(submitter_id, "알 수 없음")
                    # 해당 학생의 모든 응답 중 첫 번째 응답의 관계 데이터 사용 (보통 학생당 응답은 하나)
                    row = group.iloc[0]
                    relations = row.get(relations_col, {})
                    scores_given = []

                    # 유효한 관계 데이터(dict)인지, 내용은 있는지 확인
                    if isinstance(relations, dict) and relations:
                        for target_id, info in relations.items():
                            score = info.get('intimacy')
                            # 점수가 숫자 타입인지 확인
                            if isinstance(score, (int, float)):
                                scores_given.append(score)

                    if scores_given: # 준 점수가 하나라도 있을 경우
                        avg_given = sum(scores_given) / len(scores_given)
                        given_scores_list.append({
                            'submitter_id': submitter_id,
                            'submitter_name': submitter_name,
                            'average_score_given': avg_given,
                            'rated_count': len(scores_given), # 몇 명에게 점수를 매겼는지
                            'scores_list': scores_given # 분포 분석용 점수 목록
                        })
                if not given_scores_list: # 계산된 결과가 없으면 빈 DataFrame 반환
                    return pd.DataFrame(columns=['submitter_id', 'submitter_name', 'average_score_given', 'rated_count', 'scores_list'])
                return pd.DataFrame(given_scores_list)

            # 계산 실행
            avg_given_df = calculate_given_scores(analysis_df, students_map)

            if not avg_given_df.empty:
                # 평균 준 점수 기준 정렬
                avg_given_df = avg_given_df.sort_values(by='average_score_given', ascending=False)

                # 시각화: 평균 준 점수 막대 그래프
                fig_given = px.bar(avg_given_df,
                                   x='submitter_name',
                                   y='average_score_given',
                                   title="평균 '준' 친밀도 점수 (높을수록 다른 친구를 긍정적으로 평가)",
                                   labels={'submitter_name':'학생 이름', 'average_score_given':'평균 준 점수'},
                                   hover_data=['rated_count'], # 마우스 올리면 평가한 친구 수 표시
                                   color='average_score_given', # 점수에 따라 색상 변화
                                   color_continuous_scale=px.colors.sequential.Plasma_r) # 다른 색상 스케일 사용
                fig_given.update_layout(yaxis_range=[0,100]) # Y축 범위 0-100 고정
                st.plotly_chart(fig_given, use_container_width=True)

                # 간단 분석 요약
                try: # 데이터가 1개만 있을 경우 iloc[-1] 오류 방지
                    highest_giver = avg_given_df.iloc[0]
                    lowest_giver = avg_given_df.iloc[-1]
                    st.write(f"👍 다른 친구들에게 가장 높은 평균 점수를 준 학생: **{highest_giver['submitter_name']}** ({highest_giver['average_score_given']:.1f}점, {highest_giver['rated_count']}명 평가)")
                    st.write(f"🤔 다른 친구들에게 가장 낮은 평균 점수를 준 학생: **{lowest_giver['submitter_name']}** ({lowest_giver['average_score_given']:.1f}점, {lowest_giver['rated_count']}명 평가)")
                except IndexError:
                     st.write("점수 비교 분석을 위한 데이터가 충분하지 않습니다.")


                # --- (선택 사항) 개인별 준 점수 분포 시각화 ---
                st.markdown("---")

                # --- 3. 학급 전체 친밀도 점수 분포 (새로 추가) ---
                st.subheader("학급 전체 친밀도 점수 분포")

                all_scores_given = [] # 모든 점수를 담을 리스트
                # analysis_df의 'parsed_relations' 컬럼을 순회하며 모든 점수 추출
                # dropna()를 사용하여 'parsed_relations'가 비어있는 행은 제외
                for relations in analysis_df['parsed_relations'].dropna():
                    # relations가 dict 타입인지, 내용이 있는지 확인
                    if isinstance(relations, dict) and relations:
                        for info in relations.values():
                            score = info.get('intimacy')
                            # score가 숫자 타입인지 확인
                            if isinstance(score, (int, float)):
                                all_scores_given.append(score)

                if all_scores_given: # 추출된 점수가 있을 경우
                    # 점수 목록으로 DataFrame 생성
                    scores_dist_df = pd.DataFrame({'점수': all_scores_given})

                    # 히스토그램 생성
                    fig_overall_dist = px.histogram(
                        scores_dist_df,
                        x='점수', # X축은 점수
                        title="학급 전체에서 학생들이 매긴 '친밀도 점수' 분포",
                        labels={'점수': '친밀도 점수 (0: 매우 어려움 ~ 100: 매우 친함)'},
                        nbins=20, # 막대의 개수 (20개 구간으로 나눔, 조절 가능)
                        range_x=[0, 100] # X축 범위 0-100으로 고정
                    )
                    # 그래프 레이아웃 추가 설정
                    fig_overall_dist.update_layout(
                        bargap=0.1, # 막대 사이 간격
                        yaxis_title="응답 빈도수" # Y축 제목
                    )
                    st.plotly_chart(fig_overall_dist, use_container_width=True)

                    # 간단한 통계 정보 추가 (선택 사항)
                    try:
                        avg_overall = scores_dist_df['점수'].mean()
                        median_overall = scores_dist_df['점수'].median()
                        stdev_overall = scores_dist_df['점수'].std()
                        st.write(f"**전체 평균 점수:** {avg_overall:.1f}")
                        st.write(f"**중앙값:** {median_overall:.0f}")
                        st.write(f"**표준편차:** {stdev_overall:.1f}")
                        st.caption("""
                        * 히스토그램은 학생들이 다른 친구들에게 매긴 모든 점수들이 어떤 구간에 얼마나 분포하는지를 보여줍니다.
                        * 막대가 높을수록 해당 점수 구간을 선택한 응답이 많다는 의미입니다.
                        * 분포가 왼쪽(낮은 점수) 또는 오른쪽(높은 점수)으로 치우쳐 있는지, 혹은 넓게 퍼져있는지(표준편차) 등을 통해 학급의 전반적인 관계 분위기를 파악할 수 있습니다.
                        """)
                    except Exception as stat_e:
                        st.warning(f"통계 계산 중 오류: {stat_e}")
                # --- 4. 관계 상호성 분석 (새로 추가) ---
                st.markdown("---")        
                st.subheader("관계 상호성 분석 (Reciprocity)")

                # 함수: 상호 평가 점수 계산 및 관계 유형 분류
                @st.cache_data # 계산 결과를 캐싱
                def analyze_reciprocity(df, student_map):
                    # 입력 데이터 유효성 검사
                    if df.empty or 'parsed_relations' not in df.columns or 'submitter_id' not in df.columns or not student_map:
                        return pd.DataFrame(columns=['학생 A', '학생 B', 'A->B 점수', 'B->A 점수', '관계 유형'])

                    # 1. 모든 A->B 점수를 빠르게 조회할 수 있는 딕셔너리 생성
                    #   Key: (주는학생ID, 받는학생ID), Value: 점수
                    score_lookup = {}
                    for index, row in df.iterrows():
                        submitter_id = row['submitter_id']
                        relations = row.get('parsed_relations', {})
                        if isinstance(relations, dict):
                            for target_id, info in relations.items():
                                # target_id가 실제 학급 학생인지 확인 (students_map 사용)
                                if target_id in student_map:
                                    score = info.get('intimacy')
                                    if isinstance(score, (int, float)):
                                        score_lookup[(submitter_id, target_id)] = score

                    # 2. 모든 학생 쌍에 대해 상호 점수 확인
                    student_ids = list(student_map.keys())
                    reciprocal_data = []

                    # 모든 가능한 학생 쌍 (A, B) 조합 생성 (itertools 사용)
                    for id_a, id_b in itertools.combinations(student_ids, 2):
                        # A가 B에게 준 점수 조회
                        score_a_to_b = score_lookup.get((id_a, id_b))
                        # B가 A에게 준 점수 조회
                        score_b_to_a = score_lookup.get((id_b, id_a))

                        # 둘 다 서로 평가한 경우에만 분석 대상에 포함
                        if score_a_to_b is not None and score_b_to_a is not None:
                            name_a = student_map.get(id_a, "알 수 없음")
                            name_b = student_map.get(id_b, "알 수 없음")
                            reciprocal_data.append({
                                '학생 A': name_a,
                                '학생 B': name_b,
                                'A->B 점수': score_a_to_b,
                                'B->A 점수': score_b_to_a
                            })

                    if not reciprocal_data: # 상호 평가 데이터가 없으면 빈 DataFrame 반환
                        return pd.DataFrame(columns=['학생 A', '학생 B', 'A->B 점수', 'B->A 점수', '관계 유형'])

                    reciprocity_df = pd.DataFrame(reciprocal_data)

                    # 3. 관계 유형 분류 함수 정의
                    def categorize_relationship(row, high_threshold=75, low_threshold=35): # 기준점수 조절 가능
                        score_ab = row['A->B 점수']
                        score_ba = row['B->A 점수']
                        high_a = score_ab >= high_threshold
                        low_a = score_ab <= low_threshold
                        high_b = score_ba >= high_threshold
                        low_b = score_ba <= low_threshold

                        if high_a and high_b: return "✅ 상호 높음"
                        if low_a and low_b: return "⚠️ 상호 낮음"
                        if high_a and low_b: return f"↗️ {row['학생 A']} > {row['학생 B']} (일방 높음)"
                        if low_a and high_b: return f"↖️ {row['학생 B']} > {row['학생 A']} (일방 높음)"
                        # 필요시 중간 유형 추가 가능
                        return "↔️ 혼합/중간"

                    # DataFrame에 '관계 유형' 컬럼 추가
                    reciprocity_df['관계 유형'] = reciprocity_df.apply(categorize_relationship, axis=1)
                    return reciprocity_df

                # 상호성 분석 실행
                reciprocity_results_df = analyze_reciprocity(analysis_df, students_map)

                if not reciprocity_results_df.empty:
                    st.write("서로 점수를 매긴 학생 쌍 간의 관계 유형입니다.")

                    # 요약 통계: 관계 유형별 개수
                    type_counts = reciprocity_results_df['관계 유형'].value_counts()
                    st.write("##### 관계 유형별 분포:")
                    st.dataframe(type_counts)
                    # 파이 차트 추가 (선택 사항)
                    # fig_pie = px.pie(type_counts, values=type_counts.values, names=type_counts.index, title="관계 유형 비율")
                    # st.plotly_chart(fig_pie, use_container_width=True)


                    # 상세 테이블: 상호 평가 목록
                    st.write("##### 상세 관계 목록:")
                    # 컬럼 순서 및 이름 변경하여 표시 (선택 사항)
                    display_df = reciprocity_results_df[['학생 A', '학생 B', 'A->B 점수', 'B->A 점수', '관계 유형']]
                    st.dataframe(display_df, use_container_width=True, hide_index=True)

                    # (고급/선택) 네트워크 그래프 시각화
                    # if st.checkbox("관계 네트워크 그래프 보기 (상호 평가 기반)"):
                    #     st.info("네트워크 그래프 기능은 준비 중입니다.")
                    #     # NetworkX, Pyvis 등을 사용하여 그래프 생성 및 표시 로직 추가

                else:
                    st.write("상호 평가 데이터가 부족하여 관계 상호성 분석을 할 수 없습니다.")
                    st.caption("학생들이 서로에 대해 충분히 평가해야 이 분석이 가능합니다.")        
                st.markdown("---")        
                st.subheader("개인별 '준' 점수 분포 확인")
                # 학생 이름 목록 생성 (submitter_name 사용)
                # 학생 이름 목록 생성 (avg_given_df에서 가져옴 - 이전 단계에서 생성됨)
                if not avg_given_df.empty:
                    student_names_for_given = ["-- 학생 선택 --"] + sorted(avg_given_df['submitter_name'].unique())
                    student_to_view = st.selectbox(
                        "점수 내역을 확인할 학생 선택:", # 레이블 약간 변경
                        options=student_names_for_given,
                        key="given_score_detail_select" # 키 변경
                    )

                    if student_to_view != "-- 학생 선택 --":
                        # --- !!! 선택된 학생의 'parsed_relations' 데이터 추출 및 변환 !!! ---
                        # analysis_df에서 해당 학생의 행 찾기
                        student_data_row = analysis_df[analysis_df['submitter_name'] == student_to_view]

                        if not student_data_row.empty:
                            relations_dict = student_data_row.iloc[0].get('parsed_relations', {})
                            individual_ratings = [] # 막대 그래프용 데이터 리스트

                            if isinstance(relations_dict, dict) and relations_dict:
                                for classmate_id, info in relations_dict.items():
                                    score = info.get('intimacy')
                                    if isinstance(score, (int, float)):
                                        # students_map (ID->이름 맵)을 사용하여 이름 가져오기
                                        classmate_name = students_map.get(classmate_id, f"ID:{classmate_id[:4]}...")
                                        individual_ratings.append({"평가 대상 학생": classmate_name, "내가 준 점수": score})

                            if individual_ratings:
                                # --- !!! 데이터프레임 생성 및 막대 그래프 그리기 !!! ---
                                ratings_df = pd.DataFrame(individual_ratings)
                                # 점수 기준으로 정렬 (높은 점수 -> 낮은 점수)
                                ratings_df = ratings_df.sort_values(by="내가 준 점수", ascending=False)

                                fig_individual_bar = px.bar(
                                    ratings_df,
                                    x="평가 대상 학생",   # X축: 친구 이름
                                    y="내가 준 점수",    # Y축: 해당 친구에게 준 점수
                                    title=f"'{student_to_view}' 학생이 다른 친구들에게 준 점수",
                                    labels={"평가 대상 학생": "친구 이름", "내가 준 점수": "친밀도 점수"},
                                    range_y=[0, 100],      # Y축 범위 0-100 고정
                                    color="내가 준 점수",  # 점수에 따라 색상 지정
                                    color_continuous_scale=px.colors.sequential.Viridis_r # 색상 스케일
                                )
                                # X축 레이블 정렬 (점수 높은 순)
                                fig_individual_bar.update_layout(xaxis={'categoryorder':'total descending'})
                                st.plotly_chart(fig_individual_bar, use_container_width=True)
                                # --- !!! 히스토그램 코드를 이 막대 그래프 코드로 대체 !!! ---
                            else:
                                st.write(f"'{student_to_view}' 학생이 준 점수 데이터가 없습니다.")
                        else:
                             st.warning(f"'{student_to_view}' 학생의 응답 데이터를 찾을 수 없습니다.") # analysis_df에 해당 학생 row가 없는 경우     
        
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
            st.header("✨ AI 기반 심층 분석 (Gemini)")

            # 세션에서 API 키 확인
            api_key = st.session_state.get('gemini_api_key')



            if api_key:
                st.success("✅ Gemini API 키가 활성화되어 AI 분석 기능을 사용할 수 있습니다.")
                st.markdown("---")

                # --- AI 분석 기능 선택 ---
                analysis_option = st.selectbox(
                    "어떤 내용을 분석하시겠어요?",
                    ["선택하세요", "학생 고민 전체 요약", "학생별 관계 프로파일 생성", "학급 전체 관계 요약 (준비중)", "주요 키워드 추출 (준비중)"]
                )

                if analysis_option == "학생 고민 전체 요약":
                    st.subheader("학생 고민 전체 요약")
                    # analysis_df에 'concern' 컬럼이 있는지, 데이터가 있는지 확인
                    if 'concern' in analysis_df.columns and not analysis_df['concern'].isnull().all():
                                                # --- !!! 여기!!! all_concerns 변수 정의 추가 !!! ---
                        # 'concern' 컬럼에서 실제 내용이 있는 텍스트만 추출 (None, 빈 문자열, "없다", "없음" 제외)
                        valid_concerns = []
                        for item in analysis_df['concern']:
                            if isinstance(item, str) and item.strip() and item.strip().lower() not in ['없다', '없음']:
                                valid_concerns.append(item.strip())
                        all_concerns = valid_concerns # 최종 리스트 할당
                        # ------------------------------------------------

                        # 이제 all_concerns 변수가 정의되었으므로 아래 코드 사용 가능
                        if all_concerns:
                            # 요약 버튼
                            if st.button("AI 요약 실행하기", key="summarize_concerns"):
                                with st.spinner("AI가 고민 내용을 요약 중입니다..."):
                                    # 프롬프트 구성
                                    prompt = f"""
                                    다음은 학생들이 익명으로 작성한 학교생활 고민 내용들입니다.
                                    각 고민 내용은 "-----"로 구분되어 있습니다.
                                    전체 내용을 바탕으로 주요 고민 주제 3~5가지와 각 주제별 핵심 내용을 요약해주세요.
                                    결과는 한국어 불렛포인트 형태로 명확하게 제시해주세요.

                                    고민 목록:
                                    { "-----".join(all_concerns) }

                                    요약:
                                    """
                                    # AI 호출
                                    summary = call_gemini(prompt, api_key)
                                    # 결과 표시
                                    st.markdown("#### AI 요약 결과:")
                                    st.info(summary) # 또는 st.text_area
                        else:
                            st.info("요약할 만한 유효한 고민 내용이 없습니다.")
                    else:
                        st.warning("분석할 'concern' 데이터가 없습니다.")
                elif analysis_option == "학생별 관계 프로파일 생성":
                    st.subheader("학생별 관계 프로파일 생성")
                    if students_map:
                        student_names_list = ["-- 학생 선택 --"] + sorted(list(students_map.values()))
                        selected_student_name = st.selectbox("분석할 학생을 선택하세요:", student_names_list, key="profile_student_select")

                        if selected_student_name != "-- 학생 선택 --":
                            selected_student_id = next((sid for sid, name in students_map.items() if name == selected_student_name), None)

                            if selected_student_id:
                                analysis_type = 'student_profile' # 분석 유형 정의
                                # 세션 상태 키 정의
                                session_key_result = f"ai_result_{selected_student_id}_{analysis_type}"
                                session_key_comment = f"ai_comment_{selected_student_id}_{analysis_type}"
                                # --- 1. 캐시된 결과 조회 ---
                                cached_result = None
                                generated_time = None
                                cache_response = None
                                cached_comment = "" # 기본 빈 문자열
                                try:
                                    # Supabase 객체 유효성 확인
                                    if not supabase:
                                        raise ConnectionError("Supabase 클라이언트가 유효하지 않습니다.")

                                    st.write(f"DEBUG: Checking cache for survey {selected_survey_id}, student {selected_student_id}") # 디버깅
                                    cache_query = supabase.table("ai_analysis_results") \
                                        .select("result_text, generated_at") \
                                        .eq("survey_instance_id", selected_survey_id) \
                                        .eq("student_id", selected_student_id) \
                                        .eq("analysis_type", analysis_type) \
                                        .maybe_single() \
                                        # .execute()
                                    try:
                                        cache_response = cache_query.execute()
                                        st.write(f"DEBUG: Cache query response type: {type(cache_response)}") # 타입 확인
                                        if cache_response is not None:
                                            if hasattr(cache_response, 'data') and cache_response.data:
                                                cached_result = cache_response.data.get("result_text")
                                                generated_time = pd.to_datetime(cache_response.data.get("generated_at")).strftime('%Y-%m-%d %H:%M') # 시간 포맷 변경
                                                st.caption(f"💾 이전에 분석된 결과입니다. (분석 시각: {generated_time})")
                                                st.info(cached_result) # 캐시된 결과 바로 표시
                                        else:
                                            # execute() 자체가 None 반환 또는 실패 시
                                            st.warning("캐시된 결과를 조회하는 중 문제가 발생했습니다 (응답 객체 없음). AI 분석을 새로 실행합니다.")
                                            print("Supabase cache query execute() returned None or failed.")
                                    except Exception as exec_e_cache:
                                        st.warning(f"캐시 조회 쿼리 실행 오류: {exec_e_cache}")
                                        cache_response = None # 오류 시 None 처리
                                    
                                except ConnectionError as ce:
                                    st.error(f"데이터베이스 연결 오류: {ce}")
                                    # 필요시 st.stop()
                                except Exception as e:
                                    st.warning(f"캐시된 분석 결과 조회 중 오류: {e}")
                                    
                                # --- 2. 분석 실행 버튼 (캐시 없거나, 다시 분석 원할 때) ---
                                regenerate = st.button("🔄 AI 분석 실행/재실행", key=f"run_ai_{selected_student_id}")
                                if regenerate: # 버튼 클릭 할때
                                # if st.button(f"'{selected_student_name}' 학생 프로파일 생성하기", key="generate_profile"):
                                    with st.spinner(f"{selected_student_name} 학생의 관계 데이터를 분석 중입니다..."):
                                        previous_comment = st.session_state.get(session_key_comment, "") # 현재 세션의 코멘트 가져오기    
                                        # 1. 선택된 학생의 응답 데이터 찾기
                                        student_response_row = analysis_df[analysis_df['submitter_id'] == selected_student_id]
                                        if not student_response_row.empty:
                                            my_ratings_data = student_response_row.iloc[0].get('parsed_relations', {})
                                            my_praise = student_response_row.iloc[0].get('praise_friend')
                                            my_praise_reason = student_response_row.iloc[0].get('praise_reason')
                                            my_difficult = student_response_row.iloc[0].get('difficult_friend')
                                            my_difficult_reason = student_response_row.iloc[0].get('difficult_reason')
                                            # ... 기타 필요한 정보
                                
                                        else:
                                            my_ratings_data, my_praise, my_praise_reason, my_difficult, my_difficult_reason = {}, None, None, None, None
                                        # --- !!! UUID -> 이름 변환 및 데이터 형식 재구성 !!! ---
                                        # 1. 내가 준 점수: UUID 키를 이름으로 변경하여 텍스트 생성
                                                                                # 2. 선택된 학생이 받은 점수 정보 (avg_df 활용 - 이전 탭에서 계산됨)
                                        received_avg_info = avg_df[avg_df['student_id'] == selected_student_id]
                                        if not received_avg_info.empty:
                                            avg_score = received_avg_info.iloc[0].get('average_score')
                                            received_count = received_avg_info.iloc[0].get('received_count')
                                        else:
                                            avg_score, received_count = None, 0

                                        # 3. 누가 이 학생을 칭찬/어렵다고 했는지 찾기 (analysis_df 전체 순회 필요)
                                        praised_by = analysis_df[analysis_df['praise_friend'] == selected_student_name]['submitter_name'].tolist()
                                        difficult_by = analysis_df[analysis_df['difficult_friend'] == selected_student_name]['submitter_name'].tolist()
                                        my_ratings_text_parts = []
                                        if isinstance(my_ratings_data, dict):
                                            for classmate_id, info in my_ratings_data.items():
                                                # students_map을 사용하여 ID를 이름으로 변환
                                                classmate_name = students_map.get(classmate_id, f"ID: {classmate_id[:4]}...") # 이름 없으면 ID 축약 표시
                                                score = info.get("intimacy", "점수 없음")
                                                my_ratings_text_parts.append(f"{classmate_name}: {score}점")
                                        my_ratings_summary = ", ".join(my_ratings_text_parts) if my_ratings_text_parts else "평가 없음"

                                        # 2. 나를 칭찬한 학생: UUID 리스트를 이름 리스트로 변경
                                        praised_by_names = [students_map.get(sid, f"ID: {sid[:4]}...") for sid in praised_by]
                                        praised_by_text = ", ".join(praised_by_names) if praised_by_names else "없음"

                                        # 3. 나를 어렵다고 한 학생: UUID 리스트를 이름 리스트로 변경
                                        difficult_by_names = [students_map.get(sid, f"ID: {sid[:4]}...") for sid in difficult_by]
                                        difficult_by_text = ", ".join(difficult_by_names) if difficult_by_names else "없음"
                                        # ---------------------------------------------------

                                        # --- 프롬프트 구성 (ID 대신 이름 사용) ---
                                        prompt = f"""
                                        다음은 '{selected_student_name}' 학생의 교우관계 데이터입니다. 분석 시 학생 ID 대신 반드시 학생 이름을 사용해주세요.

                                        1.  '{selected_student_name}' 학생이 다른 친구들에게 준 친밀도 점수: [{my_ratings_summary}] (0: 매우 어려움, 100: 매우 친함)
                                        2.  다른 친구들이 '{selected_student_name}' 학생에게 준 평균 친밀도 점수: {f'{avg_score:.1f}점' if avg_score is not None else '데이터 없음'} ({received_count}명 평가)
                                        3.  '{selected_student_name}' 학생이 칭찬한 친구: {my_praise or '없음'} (이유: {my_praise_reason or '없음'})
                                        4.  '{selected_student_name}' 학생을 칭찬한 친구 목록: [{praised_by_text}]
                                        5.  '{selected_student_name}' 학생이 어렵다고 한 친구: {my_difficult or '없음'} (이유: {my_difficult_reason or '없음'})
                                        6.  '{selected_student_name}' 학생을 어렵다고 한 친구 목록: [{difficult_by_text}]
                                        {f"참고: 이 학생에 대한 이전 교사 코멘트: {previous_comment}" if previous_comment else ""}
                                        위 정보를 종합하여 '{selected_student_name}' 학생의 학급 내 교우관계 특징, 사회성(예: 관계 주도성, 수용성), 긍정적/부정적 관계 양상, 그리고 교사가 관심을 가져야 할 부분(잠재적 강점 또는 어려움)에 대해 구체적으로 분석하고 해석해주세요. 분석 결과에는 학생 ID가 아닌 학생 이름만 포함하여 한국어로 작성해주세요.
                                        """

                                        # --- AI 호출 및 결과 표시 ---
                                        new_analysis_result = call_gemini(prompt, api_key) # utils 사용 가정
                                        # --- 결과 처리 및 캐시 저장/업데이트 ---
                                        if new_analysis_result and not new_analysis_result.startswith("오류:"):
                                            st.session_state[session_key_result] = new_analysis_result
                                            # 재분석 시 기존 코멘트는 유지하거나 지울 수 있음 (현재는 유지)
                                            # st.session_state[session_key_comment] = "" # 재분석 시 코멘트 초기화 원하면
                                            st.success("✅ AI 분석 완료! 아래 결과를 확인하고 저장하세요.")
                                        else:
                                            # AI 호출 실패 시 오류 메시지 표시
                                            st.error(new_analysis_result or "AI 분석 중 알 수 없는 오류")
                                            if session_key_result in st.session_state:
                                                del st.session_state[session_key_result] # 실패 시 이전 결과도 지움
                                
                                current_result = st.session_state.get(session_key_result)
                                if current_result:
                                    st.markdown(f"#### '{selected_student_name}' 학생 관계 프로파일 (AI 분석):")
                                    st.info(current_result) # 또는 st.text_area
                                     
                                    # --- 4. 교사 코멘트 입력 및 저장 버튼 ---
                                    st.markdown("---")
                                    st.subheader("✍️ 교사 코멘트 추가 및 저장")
                                    # 세션 상태 또는 DB에서 불러온 기존 코멘트를 기본값으로 사용
                                    current_comment = st.session_state.get(session_key_comment, cached_comment) # 세션>DB 순서
                                    teacher_comment_input = st.text_area(
                                        "분석 결과에 대한 교사 의견 또는 추가 메모:",
                                        value=current_comment,
                                        height=150,
                                        key=f"comment_input_{selected_student_id}"
                                    )       
                                    
                                    if st.button("💾 분석 결과 및 코멘트 저장하기", key=f"save_ai_{selected_student_id}"):
                                        if not current_result:
                                            st.warning("저장할 AI 분석 결과가 없습니다. 먼저 분석을 실행해주세요.")
                                        else:
                                            # DB에 결과 저장 (Upsert 사용: 없으면 Insert, 있으면 Update)
                                            try:
                                                # upsert 할 데이터 준비
                                                data_to_save = {
                                                    'survey_instance_id': selected_survey_id,
                                                    'student_id': selected_student_id,
                                                    'analysis_type': analysis_type,
                                                    'result_text': new_analysis_result,
                                                    'generated_at': datetime.datetime.now().isoformat(), # 현재 시각
                                                    # 'prompt_hash': prompt_hash # 선택 사항
                                                }
                                                # unique 제약 조건이 있는 컬럼들 지정하여 충돌 시 업데이트
                                                upsert_response = supabase.table("ai_analysis_results") \
                                                    .upsert(data_to_save, on_conflict='survey_instance_id, student_id, analysis_type') \
                                                    .execute()

                                                # upsert 성공 여부 확인 (API v2에서는 data가 없을 수 있음)
                                                if not hasattr(upsert_response, 'error') or upsert_response.error is None:
                                                    st.success("✅ 분석 결과가 데이터베이스에 저장/업데이트되었습니다.")
                                                else:
                                                    st.warning(f"분석 결과를 DB에 저장하는 중 오류 발생: {upsert_response.error}")

                                            except Exception as db_e:
                                                st.warning(f"분석 결과를 DB에 저장하는 중 예외 발생: {db_e}")
                                                
                                        # if profile_result and not profile_result.startswith("오류:"):
                                        #     st.markdown("---")
                                        #     st.subheader("📄 분석 결과 저장/출력")

                                        #     # PDF 다운로드 버튼
                                        #     try:
                                        #         # PDF 데이터 생성 시도
                                        #         pdf_data = create_pdf(profile_result, f"{selected_survey_name} - AI 분석 결과")
                                        #         if pdf_data: # create_pdf가 bytearray 또는 bytes를 성공적으로 반환 시
                                        #             # --- !!! bytearray를 bytes로 변환 !!! ---
                                        #             try:
                                        #                 pdf_bytes_for_button = bytes(pdf_data) # 타입 변환 시도
                                        #             except Exception as convert_e:
                                        #                 st.error(f"PDF 데이터 형식 변환 오류: {convert_e}")
                                        #                 pdf_bytes_for_button = None # 변환 실패 시 None
                                        #             # -----------------------------------------
                                        #             if pdf_bytes_for_button: # PDF 생성 성공 시에만 버튼 활성화
                                        #                 current_time = datetime.datetime.now().strftime("%Y%m%d_%H%M")
                                        #                 pdf_filename = f"AI_분석결과_{selected_class_name}_{selected_survey_name}_{current_time}.pdf"

                                        #                 st.download_button(
                                        #                     label="PDF로 저장하기",
                                        #                     data=pdf_data,
                                        #                     file_name=pdf_filename,
                                        #                     mime="application/pdf"
                                        #                 )
                                        #         # else:
                                        #         #     # create_pdf 함수 내부에서 오류 메시지가 이미 표시되었을 것임
                                        #         #     st.warning("PDF 생성에 실패하여 다운로드 버튼을 비활성화합니다.")

                                        #     except Exception as pdf_e:
                                        #         st.error(f"PDF 다운로드 버튼 생성 중 오류: {pdf_e}")
                            else:
                                st.warning("학생을 선택해주세요.")
                    else:
                        st.info("분석할 학생 정보가 없습니다.")
                elif analysis_option == "학급 전체 관계 요약 (준비중)":
                    st.info("감성 분석 기능은 준비 중입니다.")
                    # 여기에 감성 분석 로직 추가 (difficult_reason 컬럼 사용)

                elif analysis_option == "주요 키워드 추출 (준비중)":
                    st.info("키워드 추출 기능은 준비 중입니다.")
                    # 여기에 키워드 추출 로직 추가 (여러 텍스트 컬럼 활용 가능)
                # 다른 분석 옵션 추가 가능...

            else:
                # API 키가 없을 때 안내 메시지 (기존과 동일)
                st.warning("⚠️ AI 기반 분석 기능을 사용하려면 Gemini API 키가 필요합니다.")
                st.markdown("""
                    API 키를 입력하면 학생들의 서술형 응답에 대한 자동 요약, 주요 키워드 추출,
                    관계 패턴에 대한 심층적인 해석 등 추가적인 분석 결과를 얻을 수 있습니다.

                    API 키는 **왼쪽 사이드바의 '⚙️ 설정' 메뉴**에서 입력할 수 있습니다.
                    키 발급은 [Google AI Studio](https://aistudio.google.com/app/apikey)에서 가능합니다.
                """)
                if st.button("설정 페이지로 이동", key="go_to_settings"):
                     st.switch_page("pages/4_⚙️_설정.py") # 페이지 이동 버튼 (Streamlit 1.28 이상)
 



    # ... (데이터 로드 실패 시 등 나머지 코드) ...

    else:
        # 데이터 로드 실패 시 (load_analysis_data 함수 내에서 이미 경고/오류 표시됨)
        pass

else:
    st.info("분석할 학급과 설문을 선택해주세요.")