# pages/3_📊_분석_대시보드.py
import streamlit as st
from supabase import Client, PostgrestAPIResponse
import pandas as pd
import json
import plotly.express as px # 시각화를 위해 Plotly 추가 (pip install plotly)
import os
from utils import call_gemini

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
                        selected_student_name = st.selectbox("분석할 학생을 선택하세요:", student_names_list)

                        if selected_student_name != "-- 학생 선택 --":
                            # # 선택된 학생 ID 찾기
                            selected_student_id = next((sid for sid, name in students_map.items() if name == selected_student_name), None)

                            if selected_student_id:
                                if st.button(f"'{selected_student_name}' 학생 프로파일 생성하기", key="generate_profile"):
                                    with st.spinner(f"{selected_student_name} 학생의 관계 데이터를 분석 중입니다..."):

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

                                        위 정보를 종합하여 '{selected_student_name}' 학생의 학급 내 교우관계 특징, 사회성(예: 관계 주도성, 수용성), 긍정적/부정적 관계 양상, 그리고 교사가 관심을 가져야 할 부분(잠재적 강점 또는 어려움)에 대해 구체적으로 분석하고 해석해주세요. 분석 결과에는 학생 ID가 아닌 학생 이름만 포함하여 한국어로 작성해주세요.
                                        """
                                        # st.write("--- DEBUG: Generated Prompt ---") # 프롬프트 확인용 (선택 사항)
                                        # st.text(prompt)
                                        # st.write("--- END DEBUG ---")

                                        # --- AI 호출 및 결과 표시 ---
                                        profile_result = call_gemini(prompt, api_key) # utils 사용 가정
                                        st.markdown(f"#### '{selected_student_name}' 학생 관계 프로파일 (AI 분석):")
                                        st.info(profile_result) # 또는 st.text_area
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