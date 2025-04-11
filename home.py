# Home.py (수정된 최종 구조)
import streamlit as st
from supabase import create_client, Client, PostgrestAPIResponse
from passlib.context import CryptContext
import time
import os
import pandas as pd # 학생 설문 로직 위해 필요
import json         # 학생 설문 로직 위해 필요
from urllib.parse import urlencode # 필요시 사용

# --- 페이지 설정 (가장 먼저, 한 번만!) ---
st.set_page_config(page_title="교우관계 시스템", page_icon="🌐", layout="wide")

# --- 공통 설정 및 함수 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@st.cache_resource
def init_connection():
    url = None
    key = None
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

supabase = init_connection()

# --- 세션 상태 초기화 ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'teacher_id' not in st.session_state: st.session_state['teacher_id'] = None
if 'teacher_name' not in st.session_state: st.session_state['teacher_name'] = None
if 'gemini_api_key' not in st.session_state: st.session_state['gemini_api_key'] = None

# --- !!! 학생 설문 페이지 렌더링 함수 !!! ---
def render_student_survey(survey_id):
    st.title("📝 교우관계 설문")
    # st.set_page_config 호출 제거! (이미 위에서 호출함)
    # st.info(f"DEBUG: 설문 페이지 렌더링 시작 (survey_id: {survey_id})")

    # --- 데이터 로드 함수 (이전에 pages/_survey_student.py에 있던 내용) ---
    # @st.cache_data(ttl=600) # 캐싱은 필요시 다시 활성화
    def load_survey_data(_survey_id):
        # st.write(f"DEBUG: load_survey_data 호출됨 (ID: {_survey_id}, 타입: {type(_survey_id)})")
        if not supabase or not isinstance(_survey_id, str) or len(_survey_id) < 30:
            st.write(f"DEBUG: Supabase 연결 실패 또는 유효하지 않은 survey_id ({_survey_id})")
            return None, "DB 연결 또는 survey_id 오류", None
        try:
            # 설문 정보 조회 (class_id 포함)
            survey_response = supabase.table('surveys').select("survey_instance_id, survey_name, description, class_id").eq('survey_instance_id', _survey_id).maybe_single().execute()
            if not survey_response.data: return None, f"ID '{_survey_id}'에 해당하는 설문을 찾을 수 없습니다.", None
            survey_info = survey_response.data
            class_id = survey_info.get('class_id')
            if not class_id: return survey_info, "설문에 연결된 학급 정보가 없습니다.", None

            # 학생 명단 조회
            student_response = supabase.table('students').select("student_id, student_name").eq('class_id', class_id).order('student_name').execute()
            if not student_response.data: return survey_info, "학급에 등록된 학생이 없습니다.", None
            students_df = pd.DataFrame(student_response.data)
            return survey_info, None, students_df
        except Exception as e:
            return None, f"데이터 로딩 중 오류 발생: {e}", None

    # --- 설문 데이터 로드 ---
    survey_info, error_msg, students_df = load_survey_data(survey_id)

    if error_msg:
        st.error(error_msg)
        st.stop() # 오류 시 중단
    elif not survey_info or students_df is None:
        st.error("설문 정보를 불러올 수 없습니다. URL을 확인하거나 관리자에게 문의하세요.")
        st.stop() # 오류 시 중단
    else:

    # --- 설문 진행 코드 (기존 코드 유지) ---
        # st.title(f"📝 {survey_info.get('survey_name', '교우관계 설문')}")
        if survey_info.get('description'):
            st.markdown(survey_info['description'])
        st.divider()

        # --- 학생 본인 확인 ---
        st.subheader("1. 본인 확인")
        student_list = students_df['student_name'].tolist()
        my_name = st.selectbox(
            "본인의 이름을 선택해주세요.",
            options=[""] + sorted(student_list), # 이름 순 정렬
            index=0,
            key="my_name_select_survey" # 고유 키 지정
        )


        if my_name:
            my_student_id = students_df[students_df['student_name'] == my_name]['student_id'].iloc[0]
            st.caption(f"{my_name} 학생으로 설문을 진행합니다.")
            st.divider()

        #     # --- 관계 매핑 (슬라이더 방식) ---
        #     st.subheader("2. 친구 관계 입력")
        #     st.info("각 친구와의 관계 정도를 슬라이더를 움직여 표시해주세요.")

        #     classmates_df = students_df[students_df['student_name'] != my_name] # 본인 제외
        #     relation_mapping = {} # 관계 점수를 저장할 딕셔너리

        #     for index, row in classmates_df.iterrows():
        #         classmate_id = row['student_id']
        #         classmate_name = row['student_name']

        #         # 각 학생마다 슬라이더 생성
        #         intimacy_score = st.slider(
        #             label=f"**{classmate_name}** 와(과)의 관계 정도",
        #             min_value=0,    # 최소값 (예: 매우 어려움)
        #             max_value=100,  # 최대값 (예: 매우 친함)
        #             value=50,       # 기본값 (예: 보통)
        #             step=1,         # 단계 (1 단위로 조절)
        #             help="0에 가까울수록 어려운 관계, 100에 가까울수록 친한 관계를 의미합니다.",
        #             key=f"relation_slider_{classmate_id}" # 고유 키 필수
        #         )
        #         # 슬라이더 값 저장
        #         relation_mapping[classmate_id] = {"intimacy": intimacy_score}
        #         st.write("---") # 학생 간 구분선

        #     st.divider()

        #     # --- 추가 설문 항목 (기존과 동일) ---
        #     st.subheader("3. 추가 질문")
        #     with st.form("survey_form"):
        #         # ... (기존 추가 질문 입력 필드들) ...
        #         praise_friend = st.text_input("우리 반에서 칭찬하고 싶은(친해지고 싶은) 친구는? (없으면 비워두세요)")
        #         praise_reason = st.text_input("우리 반에서 칭찬하고 싶은(친해지고 싶은) 친구를 선택한 이유를 적어주세요. (없으면 비워두세요)")
        #         difficult_friend = st.text_input("우리 반에서 대하기 어려운 친구는? (없으면 비워두세요)")
        #         difficult_reason = st.text_input("우리 반에서 대하기 어려운 친구를 선택한 이유를 적어주세요. (없으면 비워두세요)")
        #         otherclass_friendly_name = st.text_input("다른 반에서 요즘 친한 친구는? (없으면 비워두세요)")
        #         otherclass_friendly_reason = st.text_input("다른 반에서 친한 친구를 선택한 이유를 적어주세요. (없으면 비워두세요)")
        #         otherclass_bad_name = st.text_input("다른 반에서 요즘 대하기 어려운 친구는? (없으면 비워두세요)")
        #         otherclass_bad_reason = st.text_input("다른 반에서 대하기 어려운 친구를 선택한 이유를 적어주세요. (없으면 비워두세요)")
        #         concern = st.text_area("요즘 학급이나 학교에서 어렵거나 힘든 점이 있다면 적어주세요.")
        #         teacher_message = st.text_area("그 외 선생님께 하고 싶은 말을 자유롭게 적어주세요.")

        #         submitted = st.form_submit_button("설문 제출하기")

        #         if submitted:
        #             # --- 제출 처리 (relation_mapping_json 부분은 동일) ---
        #             st.info("답변을 제출 중입니다...")
        #             try:
        #                 # 관계 매핑 데이터를 JSON 문자열로 변환
        #                 relation_mapping_json = json.dumps(relation_mapping, ensure_ascii=False)

        #                 # 응답 데이터 구성 (relation_mapping_data 컬럼 사용)
        #                 response_data = {
        #                     'survey_instance_id': final_survey_id,
        #                     'student_id': my_student_id,
        #                     'relation_mapping_data': relation_mapping_json, # 슬라이더 점수 저장
        #                     'praise_friend': praise_friend,
        #                     'praise_reason': praise_reason,
        #                     'difficult_friend': difficult_friend,
        #                     'difficult_reason': difficult_reason,
        #                     'otherclass_friendly_name': otherclass_friendly_name,
        #                     'otherclass_friendly_reason': otherclass_friendly_reason,
        #                     'otherclass_bad_name': otherclass_bad_name,
        #                     'otherclass_bad_reason': otherclass_bad_reason,
        #                     'concern': concern,
        #                     'teacher_message': teacher_message,
        #                 }

        #                 # Supabase에 데이터 삽입
        #                 insert_response = supabase.table('survey_responses').insert(response_data).execute()

        #                 # ... (제출 성공/실패 처리 로직) ...
        #                 if insert_response.data:
        #                         st.success("설문이 성공적으로 제출되었습니다. 참여해주셔서 감사합니다!")
        #                         st.balloons()
        #                 else:
        #                         st.error("설문 제출 중 오류가 발생했습니다. 다시 시도해주세요.")
        #                         print("Supabase insert error:", insert_response.error)

        #             except Exception as e:
        #                 st.error(f"설문 제출 중 오류 발생: {e}")

        # else:
        #     st.info("먼저 본인의 이름을 선택해주세요.")
        # # st.write("학생 설문 페이지 내용 (구현 필요)") # 임시 Placeholder
            # --- 기존 응답 조회 ---
            existing_response = None
            response_id_to_update = None
            try:
                # supabase 객체 유효성 재확인 (선택적이지만 안전)
                if not supabase:
                    raise ConnectionError("Supabase 클라이언트(연결)가 유효하지 않습니다.")

                # Supabase 쿼리 실행
                res: PostgrestAPIResponse = supabase.table("survey_responses") \
                    .select("*") \
                    .eq("survey_instance_id", survey_id) \
                    .eq("student_id", my_student_id) \
                    .maybe_single() \
                    .execute()

                # --- !!! 중요: res 객체가 None이 아닌지 먼저 확인 !!! ---
                if res is not None:
                    # res 객체가 존재하면 .data 속성 확인 (정상적인 응답 또는 데이터 없음)
                    if hasattr(res, 'data') and res.data: # .data 속성이 있고, 내용이 있을 때
                        existing_response = res.data
                        response_id_to_update = existing_response.get('response_id') # ID 가져오기
                        st.info("이전에 제출한 응답 기록이 있습니다. 내용을 수정 후 다시 제출할 수 있습니다.")
                        # st.write("DEBUG: Found existing response:", existing_response) # 디버깅용
                    # else: # res 객체는 있지만 .data가 없거나 비어있는 경우 (maybe_single 결과 0개 - 정상)
                    #     st.write("DEBUG: No existing response found.") # 디버깅용
                        pass # existing_response는 None으로 유지됨
                else:
                    # res 객체 자체가 None인 경우 (execute() 호출 실패 또는 심각한 오류)
                    st.error("기존 응답 조회 중 예상치 못한 문제가 발생했습니다 (응답 객체 없음).")
                    print("Supabase query execute() returned None. Check Supabase status or network.") # 콘솔 로깅

            except ConnectionError as ce:
                st.error(f"데이터베이스 연결 오류: {ce}")
                # 여기서 st.stop() 등을 사용하여 진행을 막을 수 있음
            except Exception as e:
                # Supabase 쿼리 실행 중 발생한 다른 예외 처리
                st.warning(f"기존 응답 확인 중 오류 발생: {e}")
                # 오류 발생 시에도 existing_response는 None으로 유지됨

            # 기존 응답 또는 기본값으로 초기값 설정
            initial_relation_mapping = {}
            if existing_response and existing_response.get('relation_mapping_data'):
                try:
                    # relation_mapping_data가 문자열일 경우 json.loads 사용
                    if isinstance(existing_response['relation_mapping_data'], str):
                        initial_relation_mapping = json.loads(existing_response['relation_mapping_data'])
                    # 이미 dict/list 형태일 경우 그대로 사용
                    elif isinstance(existing_response['relation_mapping_data'], (dict, list)):
                         initial_relation_mapping = existing_response['relation_mapping_data']
                except json.JSONDecodeError:
                    st.warning("기존 관계 데이터를 불러오는 데 실패했습니다.")
                except Exception as e_parse:
                     st.warning(f"기존 관계 데이터 처리 오류: {e_parse}")


            initial_values = {}
            fields_to_load = [
                'praise_friend', 'praise_reason', 'difficult_friend', 'difficult_reason',
                'otherclass_friendly_name', 'otherclass_friendly_reason',
                'otherclass_bad_name', 'otherclass_bad_reason', 'concern', 'teacher_message'
            ]
            for field in fields_to_load:
                initial_values[field] = existing_response.get(field, '') if existing_response else ''

            # --- 관계 매핑 (슬라이더 방식 - value 설정 추가) ---
            st.subheader("2. 친구 관계 입력")
            st.info("각 친구와의 관계 정도를 슬라이더를 움직여 표시해주세요.")
            relation_mapping_inputs = {}
            classmates_df = students_df[students_df['student_id'] != my_student_id]
            for index, row in classmates_df.iterrows():
                classmate_id = row['student_id']
                classmate_name = row['student_name']
                default_score = initial_relation_mapping.get(classmate_id, {}).get('intimacy', 50)
                # 슬라이더 생성 및 값 저장
                relation_mapping_inputs[classmate_id] = {
                    "intimacy": st.slider(
                        label=f"**{classmate_name}** 와(과)의 관계 정도",
                        min_value=0, max_value=100, value=int(default_score), step=1, # 정수형으로 변환
                        help="0(매우 어려움) ~ 100(매우 친함)",
                        key=f"relation_slider_{classmate_id}"
                    )
                }
                # st.write("---") # 구분선 제거 또는 유지

            st.divider()

            # --- 추가 설문 항목 (value 설정 추가) ---
            st.subheader("3. 추가 질문")
            with st.form("survey_form"):
                praise_friend = st.text_input("우리 반에서 칭찬하고 싶은 친구는?", value=initial_values['praise_friend'])
                praise_reason = st.text_area("칭찬하는 이유는 무엇인가요?", value=initial_values['praise_reason'])
                st.markdown("---")
                difficult_friend = st.text_input("우리 반에서 내가 상대적으로 대하기 어려운 친구는?", value=initial_values['difficult_friend'])
                difficult_reason = st.text_area("어렵게 느끼는 이유는 무엇인가요?", value=initial_values['difficult_reason'])
                st.markdown("---")
                other_friendly_name = st.text_input("옆 반 친구들 중 나랑 관계가 좋은 친구가 있나요?", value=initial_values['otherclass_friendly_name'])
                other_friendly_reason = st.text_area("친하게 지내는 이유는 무엇인가요?", value=initial_values['otherclass_friendly_reason'])
                st.markdown("---")
                other_bad_name = st.text_input("옆 반 친구들 중 나랑 관계가 안 좋은 친구가 있나요?", value=initial_values['otherclass_bad_name'])
                other_bad_reason = st.text_area("안 좋게 느끼는 이유는 무엇인가요?", value=initial_values['otherclass_bad_reason'])
                st.markdown("---")
                concern = st.text_area("학교생활 중 힘들었던 일이나 고민이 있나요?", value=initial_values['concern'])
                st.markdown("---")
                teacher_message = st.text_area("그 외 선생님께 하고 싶은 말을 자유롭게 적어주세요.", value=initial_values['teacher_message'])

                submit_button_label = "수정하기" if existing_response else "제출하기"
                submitted = st.form_submit_button(submit_button_label)

                if submitted:
                    st.info("답변을 처리 중입니다...")
                    # 관계 매핑 데이터를 JSON 문자열로 변환
                    relation_mapping_json = json.dumps(relation_mapping_inputs, ensure_ascii=False)

                    # DB에 저장할 데이터 구성
                    response_data = {
                        'relation_mapping_data': relation_mapping_json,
                        'praise_friend': praise_friend,
                        'praise_reason': praise_reason,
                        'difficult_friend': difficult_friend,
                        'difficult_reason': difficult_reason,
                        'otherclass_friendly_name': other_friendly_name,
                        'otherclass_friendly_reason': other_friendly_reason,
                        'otherclass_bad_name': other_bad_name,
                        'otherclass_bad_reason': other_bad_reason,
                        'concern': concern,
                        'teacher_message': teacher_message,
                        # submission_time 은 DB에서 default now() 또는 update 시 자동 갱신될 수 있음
                    }

                    try:
                        if existing_response:
                            # --- UPDATE 로직 ---
                            response = supabase.table('survey_responses') \
                                .update(response_data) \
                                .eq('response_id', response_id_to_update) \
                                .execute()
                            # Supabase V2 update는 성공 시 data가 없을 수 있음
                            if response.data or (hasattr(response, 'status_code') and response.status_code == 204):
                                st.success("응답이 성공적으로 수정되었습니다. 감사합니다!")
                                st.balloons()
                            else:
                                st.error("응답 수정 중 오류가 발생했습니다.")
                                print("Update Error:", response.error if hasattr(response, 'error') else response)
                        else:
                            # --- INSERT 로직 ---
                            response_data['survey_instance_id'] = survey_id
                            response_data['student_id'] = my_student_id
                            response = supabase.table('survey_responses').insert(response_data).execute()
                            if response.data:
                                st.success("설문이 성공적으로 제출되었습니다. 참여해주셔서 감사합니다!")
                                st.balloons()
                            else:
                                st.error("설문 제출 중 오류가 발생했습니다.")
                                print("Insert Error:", response.error if hasattr(response, 'error') else response)

                    except Exception as e:
                        st.error(f"처리 중 오류 발생: {e}")

        else:
            st.info("먼저 본인의 이름을 선택해주세요.")
# --- !!! 메인 교사 페이지 렌더링 함수 !!! ---
def render_home_page():
    # st.set_page_config 호출 제거!
    st.title("🏠 교우관계 분석 시스템")

    if not st.session_state['logged_in']:
        login_tab, signup_tab = st.tabs(["로그인", "회원가입"])
        # --- 로그인 폼 ---
        with login_tab:
            st.subheader("로그인")
            with st.form("login_form"):
                # ... (기존 로그인 폼 코드) ...
                username = st.text_input("사용자 이름 (아이디)")
                password = st.text_input("비밀번호", type="password")
                submitted = st.form_submit_button("로그인")
                if submitted:
                    check_login(username, password) # check_login 호출
            st.info("관리자에게 계정 생성을 요청하세요.")
        with signup_tab:
            st.subheader("회원가입")
            with st.form("signup_form", clear_on_submit=True):
                new_username = st.text_input("사용자 이름 (아이디)", key="signup_user")
                new_teacher_name = st.text_input("교사 이름", key="signup_name")
                new_password = st.text_input("비밀번호", type="password", key="signup_pw1")
                new_password_confirm = st.text_input("비밀번호 확인", type="password", key="signup_pw2")
                new_email = st.text_input("이메일 (선택 사항)", key="signup_email") # 이메일 필드 추가시

                signup_submitted = st.form_submit_button("가입하기")

                if signup_submitted:
                    if not all([new_username, new_teacher_name, new_password, new_password_confirm]):
                        st.warning("모든 필수 항목을 입력해주세요.")
                    elif new_password != new_password_confirm:
                        st.error("비밀번호가 일치하지 않습니다.")
                    else:
                        # --- 여기에 사용자 이름/이메일 중복 확인 로직 추가 ---
                        # 예: check_username_exists(new_username) 함수 호출
                        username_exists = False # 임시
                        try:
                            res = supabase.table("teachers").select("username").eq("username", new_username).execute()
                            if res.data:
                                username_exists = True
                        except Exception as e:
                            st.error(f"사용자 이름 확인 중 오류: {e}")
                            st.stop() # 오류 시 중단

                        if username_exists:
                            st.error("이미 사용 중인 사용자 이름입니다.")
                        else:
                            # --- 여기에 비밀번호 해싱 및 Supabase insert 로직 추가 ---
                            try:
                                hashed_password = pwd_context.hash(new_password)
                                insert_res = supabase.table("teachers").insert({
                                    "username": new_username,
                                    "password_hash": hashed_password,
                                    "teacher_name": new_teacher_name,
                                    "email": new_email # 이메일 추가 시
                                }).execute()
                                if insert_res.data:
                                    st.success("회원가입이 완료되었습니다. 로그인 탭에서 로그인해주세요.")
                                else:
                                    st.error("회원가입 처리 중 오류가 발생했습니다.")
                                    print("Signup Error:", insert_res.error)
                            except Exception as e:
                                st.error(f"회원가입 중 오류 발생: {e}")
    else:
        # --- 로그인 후 환영 메시지 및 로그아웃 버튼 ---
        st.subheader(f"{st.session_state['teacher_name']} 선생님, 안녕하세요!")
        # ... (기존 환영 메시지 코드) ...
        if st.button("로그아웃"):
            logout() # logout 호출

    st.markdown("---")
    st.caption("© 2025 푸른꿈교실. All rights reserved.")


def check_login(username, password):
    if not supabase:
        st.error("데이터베이스 연결을 확인해주세요.")
        return False

    try:
        # 사용자 이름으로 교사 정보 조회
        response: PostgrestAPIResponse = supabase.table('teachers').select("teacher_id, password_hash, teacher_name").eq('username', username).execute()

        if not response.data:
            st.warning("존재하지 않는 사용자 이름입니다.")
            return False

        teacher_data = response.data[0]
        stored_hash = teacher_data.get('password_hash')
        teacher_id = teacher_data.get('teacher_id')
        teacher_name = teacher_data.get('teacher_name', username) # 이름 없으면 username 사용

        # 비밀번호 검증
        if stored_hash and pwd_context.verify(password, stored_hash):
            # 로그인 성공: 세션 상태 업데이트
            st.session_state['logged_in'] = True
            st.session_state['teacher_id'] = teacher_id
            st.session_state['teacher_name'] = teacher_name
            st.success(f"{st.session_state['teacher_name']} 선생님, 환영합니다!")
            time.sleep(1) # 잠시 메시지 보여주고 새로고침
            st.rerun() # 로그인 후 페이지 새로고침하여 UI 업데이트
            return True
        else:
            st.error("비밀번호가 올바르지 않습니다.")
            return False

    except Exception as e:
        st.error(f"로그인 중 오류 발생: {e}")
        return False

def logout():
    # 로그아웃: 세션 상태 초기화
    st.session_state['logged_in'] = False
    st.session_state['teacher_id'] = None
    st.session_state['teacher_name'] = None
    st.info("로그아웃 되었습니다.")
    time.sleep(1)
    st.rerun() # 로그아웃 후 페이지 새로고침

# --- !!! 메인 로직: URL 파라미터 확인 후 분기 !!! ---
query_params = st.query_params
final_survey_id = None # final_survey_id 정의 추가
retrieved_value = query_params.get("survey_id") # 단순화된 추출
if isinstance(retrieved_value, list) and retrieved_value: final_survey_id = retrieved_value[0]
elif isinstance(retrieved_value, str) and retrieved_value.strip(): final_survey_id = retrieved_value.strip()

# st.write(f"DEBUG: Home.py 에서 확인한 query_params: {query_params}")
# st.write(f"DEBUG: Home.py 에서 추출한 survey_id: {final_survey_id}")
# st.write(f"DEBUG: Supabase 객체 유효성: {supabase is not None}")

if final_survey_id and supabase: # 최종 추출된 ID 사용
    render_student_survey(final_survey_id)
else:
    render_home_page()