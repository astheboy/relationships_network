# Home.py (수정된 최종 구조)
import streamlit as st
from supabase import create_client, Client, PostgrestAPIResponse
from passlib.context import CryptContext
import time
import pandas as pd # 학생 설문 로직 위해 필요
import json         # 학생 설문 로직 위해 필요
from urllib.parse import urlencode # 필요시 사용

# --- 페이지 설정 (가장 먼저, 한 번만!) ---
st.set_page_config(page_title="교우관계 시스템", page_icon="🌐", layout="wide")

# --- 공통 설정 및 함수 ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

@st.cache_resource
def init_connection():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        # 앱 전체에서 사용할 수 있도록 에러 로깅 또는 None 반환
        print(f"Supabase 연결 오류: {e}")
        # st.error를 여기서 호출하면 다른 페이지 로딩에 영향을 줄 수 있음
        return None

supabase = init_connection()

# --- 세션 상태 초기화 ---
if 'logged_in' not in st.session_state: st.session_state['logged_in'] = False
if 'teacher_id' not in st.session_state: st.session_state['teacher_id'] = None
if 'teacher_name' not in st.session_state: st.session_state['teacher_name'] = None

# --- !!! 학생 설문 페이지 렌더링 함수 !!! ---
def render_student_survey(survey_id):
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
            # ... (기존 load_survey_data 함수 로직 전체) ...
            # 예시:
            survey_response = supabase.table('surveys').select("...").eq('survey_instance_id', _survey_id).single().execute()
            if not survey_response.data: return None, "설문 정보 없음", None
            survey_info = survey_response.data
            class_id = survey_info.get('class_id')
            if not class_id: return survey_info, "학급 정보 없음", None
            student_response = supabase.table('students').select("...").eq('class_id', class_id).execute()
            if not student_response.data: return survey_info, "학생 명단 없음", None
            students_df = pd.DataFrame(student_response.data)
            return survey_info, None, students_df
        except Exception as e:
            #  st.write(f"DEBUG: 데이터 로딩 중 예외 발생: {e}")
             return None, f"데이터 로딩 중 오류 발생: {e}", None

    # --- 설문 데이터 로드 ---
    survey_info, error_msg, students_df = load_survey_data(survey_id)

    if error_msg:
        st.error(error_msg)
    elif not survey_info or students_df is None:
        st.error("설문 정보를 불러올 수 없습니다. URL을 확인하거나 관리자에게 문의하세요.")
    else:
        # --- !!! 여기에 pages/_survey_student.py의 UI 및 제출 로직 전체 삽입 !!! ---

    # --- 설문 진행 코드 (기존 코드 유지) ---
        st.title(f"📝 {survey_info.get('survey_name', '교우관계 설문')}")
        if survey_info.get('description'):
            st.markdown(survey_info['description'])
        st.divider()

        # --- 학생 본인 확인 ---
        st.subheader("1. 본인 확인")
        student_list = students_df['student_name'].tolist()
        my_name = st.selectbox(
            "본인의 이름을 선택해주세요.",
            options=[""] + student_list, # 빈 값 추가
            index=0,
            key="my_name_select"
        )

        if my_name:
            my_student_id = students_df[students_df['student_name'] == my_name]['student_id'].iloc[0]
            st.caption(f"{my_name} 학생으로 설문을 진행합니다.")
            st.divider()

            # --- 관계 매핑 (슬라이더 방식) ---
            st.subheader("2. 친구 관계 입력")
            st.info("각 친구와의 관계 정도를 슬라이더를 움직여 표시해주세요.")

            classmates_df = students_df[students_df['student_name'] != my_name] # 본인 제외
            relation_mapping = {} # 관계 점수를 저장할 딕셔너리

            for index, row in classmates_df.iterrows():
                classmate_id = row['student_id']
                classmate_name = row['student_name']

                # 각 학생마다 슬라이더 생성
                intimacy_score = st.slider(
                    label=f"**{classmate_name}** 와(과)의 관계 정도",
                    min_value=0,    # 최소값 (예: 매우 어려움)
                    max_value=100,  # 최대값 (예: 매우 친함)
                    value=50,       # 기본값 (예: 보통)
                    step=1,         # 단계 (1 단위로 조절)
                    help="0에 가까울수록 어려운 관계, 100에 가까울수록 친한 관계를 의미합니다.",
                    key=f"relation_slider_{classmate_id}" # 고유 키 필수
                )
                # 슬라이더 값 저장
                relation_mapping[classmate_id] = {"intimacy": intimacy_score}
                st.write("---") # 학생 간 구분선

            st.divider()

            # --- 추가 설문 항목 (기존과 동일) ---
            st.subheader("3. 추가 질문")
            with st.form("survey_form"):
                # ... (기존 추가 질문 입력 필드들) ...
                praise_friend = st.text_input("우리 반에서 칭찬하고 싶은(친해지고 싶은) 친구는? (없으면 비워두세요)")
                praise_reason = st.text_input("우리 반에서 칭찬하고 싶은(친해지고 싶은) 친구를 선택한 이유를 적어주세요. (없으면 비워두세요)")
                difficult_friend = st.text_input("우리 반에서 대하기 어려운 친구는? (없으면 비워두세요)")
                difficult_reason = st.text_input("우리 반에서 대하기 어려운 친구를 선택한 이유를 적어주세요. (없으면 비워두세요)")
                otherclass_friendly_name = st.text_input("다른 반에서 요즘 친한 친구는? (없으면 비워두세요)")
                otherclass_friendly_reason = st.text_input("다른 반에서 친한 친구를 선택한 이유를 적어주세요. (없으면 비워두세요)")
                otherclass_bad_name = st.text_input("다른 반에서 요즘 대하기 어려운 친구는? (없으면 비워두세요)")
                otherclass_bad_reason = st.text_input("다른 반에서 대하기 어려운 친구를 선택한 이유를 적어주세요. (없으면 비워두세요)")
                concern = st.text_area("요즘 학급이나 학교에서 어렵거나 힘든 점이 있다면 적어주세요.")
                teacher_message = st.text_area("그 외 선생님께 하고 싶은 말을 자유롭게 적어주세요.")

                submitted = st.form_submit_button("설문 제출하기")

                if submitted:
                    # --- 제출 처리 (relation_mapping_json 부분은 동일) ---
                    st.info("답변을 제출 중입니다...")
                    try:
                        # 관계 매핑 데이터를 JSON 문자열로 변환
                        relation_mapping_json = json.dumps(relation_mapping, ensure_ascii=False)

                        # 응답 데이터 구성 (relation_mapping_data 컬럼 사용)
                        response_data = {
                            'survey_instance_id': final_survey_id,
                            'student_id': my_student_id,
                            'relation_mapping_data': relation_mapping_json, # 슬라이더 점수 저장
                            'praise_friend': praise_friend,
                            'praise_reason': praise_reason,
                            'difficult_friend': difficult_friend,
                            'difficult_reason': difficult_reason,
                            'otherclass_friendly_name': otherclass_friendly_name,
                            'otherclass_friendly_reason': otherclass_friendly_reason,
                            'otherclass_bad_name': otherclass_bad_name,
                            'otherclass_bad_reason': otherclass_bad_reason,
                            'concern': concern,
                            'teacher_message': teacher_message,
                        }

                        # Supabase에 데이터 삽입
                        insert_response = supabase.table('survey_responses').insert(response_data).execute()

                        # ... (제출 성공/실패 처리 로직) ...
                        if insert_response.data:
                                st.success("설문이 성공적으로 제출되었습니다. 참여해주셔서 감사합니다!")
                                st.balloons()
                        else:
                                st.error("설문 제출 중 오류가 발생했습니다. 다시 시도해주세요.")
                                print("Supabase insert error:", insert_response.error)

                    except Exception as e:
                        st.error(f"설문 제출 중 오류 발생: {e}")

        else:
            st.info("먼저 본인의 이름을 선택해주세요.")
        # st.write("학생 설문 페이지 내용 (구현 필요)") # 임시 Placeholder

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
        st.write("왼쪽 사이드바 메뉴를 통해 학급 관리, 설문 관리, 분석 대시보드 등의 기능을 이용할 수 있습니다.")

        # --- !!! 관리자일 경우 관리자 페이지 링크 표시 !!! ---
        is_admin_session = False # 세션 상태에도 관리자 여부 저장 고려 가능
        try:
            # DB에서 현재 사용자의 관리자 상태 확인 (매번 확인할 수도 있고, 로그인 시 세션에 저장할 수도 있음)
            admin_check_res = supabase.table("teachers").select("is_admin").eq("teacher_id", st.session_state['teacher_id']).single().execute()
            if admin_check_res.data and admin_check_res.data.get('is_admin'):
                is_admin_session = True
                # st.session_state['is_admin'] = True # 로그인 시 세션에 저장하는 경우
        except Exception as e:
            print(f"관리자 상태 확인 오류: {e}") # 오류는 로깅만

        if is_admin_session:
            st.page_link("pages/_관리자_페이지.py", label="👑 관리자 대시보드 가기", icon="👑")
            st.caption("관리자 전용 메뉴입니다.")
        # ----------------------------------------------------
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