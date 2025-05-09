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

# --- 받은 점수 계산 함수 ---
@st.cache_data # 입력값이 같으면 이전 계산 결과 재사용
def calculate_received_scores(_analysis_df, _students_map):
    """각 학생이 다른 학생들로부터 받은 평균 친밀도 점수를 계산합니다."""
    # 입력 DataFrame이나 map이 비어있으면 빈 DataFrame 반환
    if _analysis_df.empty or not _students_map:
        return pd.DataFrame(columns=['student_id', 'student_name', 'average_score', 'received_count'])

    # 모든 학생 ID에 대해 빈 점수 리스트 초기화
    received_scores = {student_id: [] for student_id in _students_map.keys()}

    # 전체 응답 순회
    for index, row in _analysis_df.iterrows():
        relations = row.get('parsed_relations', {}) # 파싱된 관계 데이터 가져오기
        if isinstance(relations, dict): # 데이터가 딕셔너리 형태인지 확인
            for target_student_id, relation_info in relations.items():
                score = relation_info.get('intimacy') # 친밀도 점수 가져오기
                # 점수가 유효하고, 점수를 받은 학생(target_student_id)이 학급 학생 목록에 있는지 확인
                if isinstance(score, (int, float)) and target_student_id in received_scores:
                    received_scores[target_student_id].append(score) # 해당 학생의 점수 리스트에 추가

    # 평균 계산
    avg_received_scores_list = []
    for student_id, scores in received_scores.items():
        if scores: # 받은 점수가 하나라도 있을 경우
            avg_score = sum(scores) / len(scores)
            avg_received_scores_list.append({
                'student_id': student_id,
                'student_name': _students_map.get(student_id, 'Unknown'), # ID를 이름으로 변환
                'average_score': avg_score, # 평균 점수
                'received_count': len(scores) # 받은 횟수
            })

    # 결과가 없으면 빈 DataFrame 반환
    if not avg_received_scores_list:
        return pd.DataFrame(columns=['student_id', 'student_name', 'average_score', 'received_count'])
    # 결과를 DataFrame으로 변환하여 반환
    return pd.DataFrame(avg_received_scores_list)


# --- 준 점수 계산 함수 (기존 코드 약간 수정) ---
@st.cache_data # 입력값이 같으면 이전 계산 결과 재사용
def calculate_given_scores(_analysis_df, _students_map, id_col='submitter_id', name_col='submitter_name', relations_col='parsed_relations'):
    """각 학생이 다른 학생들에게 준 평균 친밀도 점수 및 점수 목록을 계산합니다."""
    # 입력 유효성 검사
    if _analysis_df.empty or id_col not in _analysis_df.columns or not _students_map:
         return pd.DataFrame(columns=['submitter_id', 'submitter_name', 'average_score_given', 'rated_count', 'scores_list'])

    given_scores_list = []
    # submitter_id(점수를 준 학생) 기준으로 그룹화하여 순회
    for submitter_id, group in _analysis_df.groupby(id_col):
        submitter_name = _students_map.get(submitter_id, "알 수 없음")
        # 해당 학생의 여러 응답 중 첫 번째 것 사용 (보통 학생당 응답은 1개)
        row = group.iloc[0]
        relations = row.get(relations_col, {})
        scores_given = []

        if isinstance(relations, dict) and relations:
            for target_id, info in relations.items():
                # 점수를 받은 학생(target_id)이 학급 학생인지 확인
                if target_id in _students_map:
                    score = info.get('intimacy')
                    if isinstance(score, (int, float)):
                        scores_given.append(score)

        if scores_given: # 준 점수가 하나라도 있을 경우
            avg_given = sum(scores_given) / len(scores_given)
            given_scores_list.append({
                'submitter_id': submitter_id,
                'submitter_name': submitter_name,
                'average_score_given': avg_given,
                'rated_count': len(scores_given), # 평가한 학생 수
                'scores_list': scores_given # 실제 준 점수 목록
            })

    if not given_scores_list:
        return pd.DataFrame(columns=['submitter_id', 'submitter_name', 'average_score_given', 'rated_count', 'scores_list'])
    return pd.DataFrame(given_scores_list)

# --- ▼▼▼ [수정 1] analyze_reciprocity 함수 정의를 여기로 이동 ▼▼▼ ---
@st.cache_data # 계산 결과를 캐싱
def analyze_reciprocity(df, student_map):
    # 입력 데이터 유효성 검사
    if df.empty or 'parsed_relations' not in df.columns or 'submitter_id' not in df.columns or not student_map:
        return pd.DataFrame(columns=['학생 A', '학생 B', 'A->B 점수', 'B->A 점수', '관계 유형'])

    # 1. 모든 A->B 점수를 빠르게 조회할 수 있는 딕셔너리 생성
    score_lookup = {}
    for index, row in df.iterrows():
        submitter_id = row['submitter_id']
        relations = row.get('parsed_relations', {})
        if isinstance(relations, dict):
            for target_id, info in relations.items():
                if target_id in student_map:
                    score = info.get('intimacy')
                    if isinstance(score, (int, float)):
                        score_lookup[(submitter_id, target_id)] = score

    # 2. 모든 학생 쌍에 대해 상호 점수 확인
    student_ids = list(student_map.keys())
    reciprocal_data = []
    for id_a, id_b in itertools.combinations(student_ids, 2):
        score_a_to_b = score_lookup.get((id_a, id_b))
        score_b_to_a = score_lookup.get((id_b, id_a))
        if score_a_to_b is not None and score_b_to_a is not None:
            name_a = student_map.get(id_a, "알 수 없음")
            name_b = student_map.get(id_b, "알 수 없음")
            reciprocal_data.append({
                '학생 A': name_a, '학생 B': name_b,
                'A->B 점수': score_a_to_b, 'B->A 점수': score_b_to_a
            })

    if not reciprocal_data:
        return pd.DataFrame(columns=['학생 A', '학생 B', 'A->B 점수', 'B->A 점수', '관계 유형'])

    reciprocity_df_local = pd.DataFrame(reciprocal_data) # 변수 이름 충돌 방지

    # 3. 관계 유형 분류 함수 정의
    def categorize_relationship(row, high_threshold=75, low_threshold=35):
        score_ab = row['A->B 점수']
        score_ba = row['B->A 점수']
        # ... (분류 로직) ...
        if score_ab >= high_threshold and score_ba >= high_threshold: return "✅ 상호 높음"
        # ... (나머지 분류 로직) ...
        return "↔️ 혼합/중간"

    reciprocity_df_local['관계 유형'] = reciprocity_df_local.apply(categorize_relationship, axis=1)
    return reciprocity_df_local # 계산된 DataFrame 반환
# --- ▲▲▲ [수정 1] 완료 ▲▲▲ ---


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
        # --- !!! 기본 분석 함수 호출 및 결과 저장 (데이터 로드 직후) !!! ---
        try:
            # 각 함수 호출하여 결과 DataFrame/Series 저장
            avg_received_df = calculate_received_scores(analysis_df, students_map)
            avg_given_df = calculate_given_scores(analysis_df, students_map)
            reciprocity_df = analyze_reciprocity(analysis_df, students_map) # analyze_reciprocity 함수가 정의되어 있다면
            # all_scores_list = get_all_scores(analysis_df) # 전체 점수 목록 함수가 정의되어 있다면
            # overall_scores_series = pd.Series(all_scores_list) if all_scores_list else pd.Series(dtype=float)
            
            # --- ▼▼▼ [수정 1] 전체 점수 목록 계산 및 Series 생성 ▼▼▼ ---
            all_scores_given = [] # 모든 점수를 담을 리스트 초기화
            # analysis_df의 'parsed_relations' 컬럼을 순회하며 모든 점수 추출
            for relations in analysis_df['parsed_relations'].dropna():
                if isinstance(relations, dict) and relations:
                    for info in relations.values():
                        score = info.get('intimacy')
                        if isinstance(score, (int, float)):
                            all_scores_given.append(score)

            # Pandas Series 생성 (비어있을 경우 빈 Series 생성)
            overall_scores_series = pd.Series(all_scores_given, dtype=float) if all_scores_given else pd.Series(dtype=float)
            # --- ▲▲▲ [수정 1] 완료 ▲▲▲ ---
            
            st.success("✅ 기본 분석 데이터 준비 완료.") # 계산 완료 알림

        except Exception as calc_e:
             st.error(f"기본 분석 데이터 계산 중 오류: {calc_e}")
             # 오류 발생 시 빈 데이터프레임 등으로 초기화 (이후 코드 오류 방지)
             avg_received_df = pd.DataFrame()
             avg_given_df = pd.DataFrame()
             reciprocity_df = pd.DataFrame()
             overall_scores_series = pd.Series(dtype=float)
        # --- !!! 계산 완료 !!! ---
        # --- 탭 구성 (기본 분석 + AI 분석 탭) ---
        tab_list = ["📊 관계 분석", "💬 서술형 응답", "✨ AI 심층 분석"]
        tab1, tab2, tab3 = st.tabs(tab_list)

        with tab1:
            st.header("관계 분석 (친밀도 점수 기반)")

            if not avg_received_df.empty:
                st.subheader("학생별 평균 받은 친밀도 점수")
                fig_received = px.bar(avg_received_df.sort_values('average_score', ascending=False), x='student_name', y='average_score',
                                      title="평균 받은 친밀도 점수 (높을수록 긍정적 관계)",
                                      labels={'student_name':'학생 이름', 'average_score':'평균 점수'},
                                      hover_data=['received_count'], # 마우스 올리면 받은 횟수 표시
                                      color='average_score', # 점수에 따라 색상 변화
                                      color_continuous_scale=px.colors.sequential.Viridis)
                st.plotly_chart(fig_received, use_container_width=True)


                # 간단 분석
                highest = avg_received_df.iloc[0]
                lowest = avg_received_df.iloc[-1]
                st.write(f"🌟 가장 높은 평균 점수를 받은 학생: **{highest['student_name']}** ({highest['average_score']:.1f}점, {highest['received_count']}회)")
                st.write(f"😟 가장 낮은 평균 점수를 받은 학생: **{lowest['student_name']}** ({lowest['average_score']:.1f}점, {lowest['received_count']}회)")
            else:
                st.write("점수 비교 분석을 위한 데이터가 충분하지 않습니다.")

            st.divider() # 구분선 추가

            if not avg_given_df.empty:
                st.subheader("학생별 평균 준 친밀도 점수")
                # 평균 준 점수 기준 정렬
                avg_given_df = avg_given_df.sort_values(by='average_score_given', ascending=False)
                # --- !!! avg_given_df 변수 사용하여 시각화 !!! ---
                fig_given = px.bar(avg_given_df.sort_values('average_score_given', ascending=False), x='submitter_name', y='average_score_given',
                                   title="평균 '준' 친밀도 점수 (높을수록 다른 친구를 긍정적으로 평가)",
                                   labels={'submitter_name':'학생 이름', 'average_score_given':'평균 준 점수'},
                                   hover_data=['rated_count'], # 마우스 올리면 평가한 친구 수 표시
                                   color='average_score_given', # 점수에 따라 색상 변화
                                   color_continuous_scale=px.colors.sequential.Plasma_r)
                st.plotly_chart(fig_given)
                highest_giver = avg_given_df.iloc[0]
                lowest_giver = avg_given_df.iloc[-1]
                st.write(f"👍 다른 친구들에게 가장 높은 평균 점수를 준 학생: **{highest_giver['submitter_name']}** ({highest_giver['average_score_given']:.1f}점, {highest_giver['rated_count']}명 평가)")
                st.write(f"🤔 다른 친구들에게 가장 낮은 평균 점수를 준 학생: **{lowest_giver['submitter_name']}** ({lowest_giver['average_score_given']:.1f}점, {lowest_giver['rated_count']}명 평가)")

            else:
                st.write("점수 비교 분석을 위한 데이터가 충분하지 않습니다.")

            # --- (선택 사항) 개인별 준 점수 분포 시각화 ---
            st.markdown("---")

            # --- 3. 학급 전체 친밀도 점수 분포 (새로 추가) ---
            st.subheader("학급 전체 친밀도 점수 분포")
            # --- ▼▼▼ [수정 2] 미리 계산된 all_scores_given 사용 ▼▼▼ ---
            if all_scores_given: # 추출된 점수가 있을 경우 (리스트 사용)
                # 점수 목록으로 DataFrame 생성 (히스토그램용)
                scores_dist_df = pd.DataFrame({'점수': all_scores_given})

                # 히스토그램 생성 (이하 로직 동일)
                fig_overall_dist = px.histogram(
                    scores_dist_df,
                    x='점수',
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

                # 통계 정보 표시 (이제 overall_scores_series 사용 가능)
                try:
                    if not overall_scores_series.empty: # Series가 비어있지 않은지 확인
                        avg_overall = overall_scores_series.mean()
                        median_overall = overall_scores_series.median()
                        stdev_overall = overall_scores_series.std()
                        st.write(f"**전체 평균 점수:** {avg_overall:.1f}")
                        st.write(f"**중앙값:** {median_overall:.0f}")
                        st.write(f"**표준편차:** {stdev_overall:.1f}")
                    else:
                        st.write("전체 점수 데이터가 없어 통계를 계산할 수 없습니다.")
                    # ... (캡션 등) ...
                except Exception as stat_e:
                    st.warning(f"통계 계산 중 오류: {stat_e}")
            else:
                 st.write("분석할 전체 점수 데이터가 없습니다.")
                 

            st.markdown("---")        
            st.subheader("관계 상호성 분석 (Reciprocity)")



            if not reciprocity_df.empty:
                st.write("서로 점수를 매긴 학생 쌍 간의 관계 유형입니다.")

                # 요약 통계: 관계 유형별 개수
                type_counts = reciprocity_df['관계 유형'].value_counts()
                st.write("##### 관계 유형별 분포:")
                st.dataframe(type_counts)
                # 파이 차트 추가 (선택 사항)
                # fig_pie = px.pie(type_counts, values=type_counts.values, names=type_counts.index, title="관계 유형 비율")
                # st.plotly_chart(fig_pie, use_container_width=True)


                # 상세 테이블: 상호 평가 목록
                st.write("##### 상세 관계 목록:")
                # 컬럼 순서 및 이름 변경하여 표시 (선택 사항)
                display_df = reciprocity_df[['학생 A', '학생 B', 'A->B 점수', 'B->A 점수', '관계 유형']]
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
                    ["선택하세요", "학생 고민 전체 요약", "학생별 관계 프로파일 생성", "학급 전체 관계 요약", "주요 키워드 추출 (준비중)"]
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

                                    # st.write(f"DEBUG: Checking cache for survey {selected_survey_id}, student {selected_student_id}") # 디버깅
                                    cache_query = supabase.table("ai_analysis_results") \
                                        .select("result_text, generated_at") \
                                        .eq("survey_instance_id", selected_survey_id) \
                                        .eq("student_id", selected_student_id) \
                                        .eq("analysis_type", analysis_type) \
                                        .maybe_single() \
                                        # .execute()
                                    try:
                                        cache_response = cache_query.execute()
                                        # st.write(f"DEBUG: Cache query response type: {type(cache_response)}") # 타입 확인
                                        if cache_response is not None:
                                            if hasattr(cache_response, 'data') and cache_response.data:
                                                cached_result = cache_response.data.get("result_text")
                                                cached_comment = cache_response.data.get("teacher_comment", "") # 코멘트 로드, 없으면 빈 문자열
                                                generated_time = pd.to_datetime(cache_response.data.get("generated_at")).strftime('%Y-%m-%d %H:%M') # 시간 포맷 변경
                                                st.caption(f"💾 이전에 분석된 결과입니다. (분석 시각: {generated_time})")
                                                st.session_state[session_key_result] = cached_result
                                                st.session_state[session_key_comment] = cached_comment
                                        # else:
                                        #     # execute() 자체가 None 반환 또는 실패 시
                                        #     st.warning("캐시된 결과를 조회하는 중 문제가 발생했습니다 (응답 객체 없음). AI 분석을 새로 실행합니다.")
                                        #     print("Supabase cache query execute() returned None or failed.")
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
                                        received_avg_info = avg_received_df[avg_received_df['student_id'] == selected_student_id]
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
                                                    'result_text': current_result,
                                                    'teacher_comment': teacher_comment_input, # 입력된 코멘트 저장
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
                                                    st.session_state[session_key_comment] = teacher_comment_input
                                                    st.rerun() # 저장 상태 반영 위해 새로고침
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
                elif analysis_option == "학급 전체 관계 요약":
                    st.subheader("학급 전체 관계 요약")
                    analysis_type = 'class_summary' # 캐시 키로 사용

                    # --- 캐시된 결과 조회 (student_id 없이 조회) ---
                    cached_result = None
                    generated_time = None
                    cached_comment = "" # 기본 빈 문자열
                    try:
                        cache_response = supabase.table("ai_analysis_results") \
                            .select("result_text, generated_at") \
                            .eq("survey_instance_id", selected_survey_id) \
                            .is_("student_id", None) \
                            .eq("analysis_type", analysis_type) \
                            .maybe_single() \
                            .execute()
                        # ... (캐시 조회 및 표시 로직 - 이전 답변 참고) ...
                        if cache_response and cache_response.data:
                            cached_result = cache_response.data.get("result_text")
                            generated_time = pd.to_datetime(cache_response.data.get("generated_at")).strftime('%Y-%m-%d %H:%M')
                            st.caption(f"💾 이전에 분석된 결과입니다. (분석 시각: {generated_time})")
                            st.info(cached_result)

                    except Exception as e:
                        st.warning(f"캐시된 분석 결과 조회 중 오류: {e}")

                    # --- 분석 실행 버튼 ---
                    if st.button("🔄 학급 전체 AI 분석 실행/재실행", key="run_class_summary_ai"):
                        if not cached_result: st.write("AI 분석을 요청합니다...")
                        else: st.write("AI 분석을 다시 요청합니다...")

                        with st.spinner("✨ 학급 전체 관계 데이터를 종합 분석 중입니다..."):
                            # --- 프롬프트에 넣을 데이터 요약 ---
                            try:
                                # --- ▼▼▼ [수정 확인] 이제 overall_scores_series가 정의되어 있음 ▼▼▼ ---
                                if not overall_scores_series.empty: # Series가 비어있지 않을 때만 통계 계산
                                    prompt_data = {
                                        "overall_avg": overall_scores_series.mean(),
                                        "overall_median": overall_scores_series.median(),
                                        "overall_std": overall_scores_series.std(), # 표준편차도 추가 가능
                                        # --- avg_received_df, avg_given_df, reciprocity_df가 정의되었는지 확인 후 사용 ---
                                        "highest_received": avg_received_df.nlargest(3, 'average_score')[['student_name', 'average_score']].to_dict('records') if not avg_received_df.empty else [],
                                        "lowest_received": avg_received_df.nsmallest(3, 'average_score')[['student_name', 'average_score']].to_dict('records') if not avg_received_df.empty else [],
                                        "highest_given": avg_given_df.nlargest(3, 'average_score_given')[['submitter_name', 'average_score_given']].to_dict('records') if not avg_given_df.empty else [],
                                        "lowest_given": avg_given_df.nsmallest(3, 'average_score_given')[['submitter_name', 'average_score_given']].to_dict('records') if not avg_given_df.empty else [],
                                        "reciprocity_summary": reciprocity_df['관계 유형'].value_counts().to_dict() if '관계 유형' in reciprocity_df.columns and not reciprocity_df.empty else {},
                                    }
                                else:
                                    # overall_scores_series가 비어있을 경우의 데이터 (평균/중앙값 등 제외)
                                     prompt_data = {
                                        "overall_avg": "데이터 없음",
                                        "overall_median": "데이터 없음",
                                        "overall_std": "데이터 없음",
                                        "highest_received": avg_received_df.nlargest(3, 'average_score')[['student_name', 'average_score']].to_dict('records') if not avg_received_df.empty else [],
                                        "lowest_received": avg_received_df.nsmallest(3, 'average_score')[['student_name', 'average_score']].to_dict('records') if not avg_received_df.empty else [],
                                        "highest_given": avg_given_df.nlargest(3, 'average_score_given')[['submitter_name', 'average_score_given']].to_dict('records') if not avg_given_df.empty else [],
                                        "lowest_given": avg_given_df.nsmallest(3, 'average_score_given')[['submitter_name', 'average_score_given']].to_dict('records') if not avg_given_df.empty else [],
                                        "reciprocity_summary": reciprocity_df['관계 유형'].value_counts().to_dict() if '관계 유형' in reciprocity_df.columns and not reciprocity_df.empty else {},
                                    }
                                # --- ▲▲▲ [수정 확인] 완료 ▲▲▲ ---
                                # JSON으로 변환하여 프롬프트 가독성 향상 (선택 사항)
                                prompt_data_json = json.dumps(prompt_data, ensure_ascii=False, indent=2, default=lambda x: round(x, 1) if isinstance(x, float) else str(x))


                                # --- 프롬프트 구성 ---
                                prompt = f"""
                                다음은 '{selected_class_name}' 학급의 '{selected_survey_name}' 설문 결과에 대한 요약 데이터입니다:
                                ```json
                                {prompt_data_json}
                                ```
                                참고: 점수는 0(매우 어려움) ~ 100(매우 친함) 척도입니다. 'highest/lowest_received'는 다른 학생들에게 받은 평균 점수 기준, 'highest/lowest_given'은 다른 학생들에게 준 평균 점수 기준입니다. 'reciprocity_summary'는 서로 평가한 학생 쌍의 관계 유형별 개수입니다.

                                위 데이터를 바탕으로 이 학급의 전반적인 교우관계 분위기, 주요 특징, 잠재적인 그룹 형성이나 소외 경향, 긍정적/부정적 상호작용 패턴 등 학급 전체 관계에 대한 종합적인 분석과 해석을 교사가 이해하기 쉽게 한국어로 작성해주세요. 주목해야 할 점이나 교사의 개입이 필요해 보이는 부분을 포함해도 좋습니다. 반드시 학생 이름을 언급할 때는 주어진 데이터에 있는 이름을 사용하세요.
                                """

                                # --- AI 호출 ---
                                new_analysis_result = call_gemini(prompt, api_key)

                                # --- 결과 처리 및 캐시 저장 (student_id = None) ---
                                if new_analysis_result and not new_analysis_result.startswith("오류:"):
                                    st.markdown("#### 학급 전체 관계 요약 (AI 분석 결과):")
                                    # st.info(new_analysis_result)

                                    # --- !!! 수동 저장 방식으로 변경 !!! ---
                                    st.session_state[f"ai_result_{selected_survey_id}_class_summary"] = new_analysis_result
                                    st.success("✅ AI 분석 완료! 아래 코멘트와 함께 저장할 수 있습니다.")

                                else:
                                    st.error(new_analysis_result or "AI 분석 중 알 수 없는 오류")
                                    session_key_class_summary = f"ai_result_{selected_survey_id}_class_summary"
                                    if session_key_class_summary in st.session_state:
                                        del st.session_state[session_key_class_summary]

                            except Exception as e:
                                st.error(f"AI 분석 준비/실행 중 오류 발생: {e}")
                                traceback.print_exc()


                        # # --- 결과 표시 및 수동 저장 UI (학생 프로파일과 유사하게) ---
                        session_key_class_summary = f"ai_result_{selected_survey_id}_class_summary"
                        # session_key_class_comment = f"ai_comment_{selected_survey_id}_class_summary"

                        current_result = st.session_state.get(session_key_class_summary)
                        # 캐시된 결과가 있고 세션 결과가 없다면 캐시된 것을 보여줌 (페이지 첫 로드시)
                        if not current_result and cached_result:
                            current_result = cached_result
                            # 코멘트도 DB에서 불러온 값 사용
                            # current_comment = cached_comment # DB 조회 로직에서 cached_comment 설정 필요
                        # else:
                        #     current_comment = st.session_state.get(session_key_class_comment, "")

                        if current_result:
                            if not cached_result: # 캐시가 없었는데 새로 생성된 경우
                                st.markdown("#### 학급 전체 관계 요약 (AI 분석 결과):")
                                st.info(current_result)

                            st.markdown("---")
                            # st.subheader("✍️ 교사 코멘트 추가 및 저장")
                            # teacher_comment_input = st.text_area(
                            #     "분석 결과에 대한 교사 의견 또는 추가 메모:",
                            #     value=current_comment,
                            #     height=150,
                            #     key=f"comment_input_{selected_survey_id}_class_summary"
                            # )

                            if st.button("💾 분석 결과 저장하기", key=f"save_ai_{selected_survey_id}_class_summary"):
                                # DB에 저장 (Upsert - student_id는 None)
                                try:
                                    data_to_save = {
                                        'survey_instance_id': selected_survey_id,
                                        'student_id': None, # 학급 전체 요약
                                        'analysis_type': analysis_type,
                                        'result_text': current_result,
                                        # 'teacher_comment': teacher_comment_input,
                                        'generated_at': datetime.datetime.now().isoformat()
                                    }
                                    upsert_response = supabase.table("ai_analysis_results") \
                                        .upsert(data_to_save, on_conflict='survey_instance_id, student_id, analysis_type') \
                                        .execute()
                                    # if hasattr(upsert_response, 'error') and upsert_response.error:
                                    #     st.error(f"DB 저장 실패 (Supabase 오류): {upsert_response.error}")
                                    # # elif hasattr(upsert_response, 'status_code') and upsert_response.status_code in [200, 201, 204]: # 성공 상태 코드 확인 (라이브러리 버전에 따라 다를 수 있음)
                                    # else : # 간단하게 error 속성이 없거나 비어있으면 성공으로 간주
                                    st.success("✅ 분석 결과가 데이터베이스에 저장되었습니다.")
                                    # st.session_state[session_key_class_comment] = teacher_comment_input # 세션 코멘트도 업데이트
                                    st.rerun()

                                except Exception as db_e:
                                    st.error(f"DB 저장 중 예외 발생: {db_e}")

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