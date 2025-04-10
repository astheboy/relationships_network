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
    # --- Supabase 클라이언트 가져오기 ---
    @st.cache_resource
    def init_connection():
        try:
            url = st.secrets["supabase"]["url"]
            key = st.secrets["supabase"]["key"]
            return create_client(url, key)
        except Exception as e:
            # 학생 페이지에서는 오류를 간결하게 표시
            print(f"Supabase 연결 오류: {e}")
            return None

    from supabase import create_client
    supabase = init_connection()

    # --- URL 파라미터에서 설문 ID 가져오기 ---
    query_params = st.query_params
    # --- !!! 디버깅: 전체 쿼리 파라미터 확인 !!! ---
    st.write(f"DEBUG: 전체 query_params: {query_params}") # 전체 내용을 확인
    # .get()을 사용하되, 키가 없을 경우 기본값으로 빈 리스트를 주고,
    # 키가 있을 경우 반환된 리스트의 첫 번째 요소를 가져옵니다.
    # survey_id_list = query_params.get("survey_id", [])
    # survey_id = survey_id_list[0] if survey_id_list else None

    # # --- !!! 디버깅: survey_id 값 확인 !!! ---
    # st.write(f"DEBUG: URL에서 가져온 survey_id: {survey_id}")

    # # --- !!! 디버깅: Supabase 연결 확인 !!! ---
    # st.write(f"DEBUG: Supabase 연결 상태: {'성공' if supabase else '실패'}")
    # --- !!! 수정된 ID 추출 로직 !!! ---
    # .get()으로 값을 가져오고 타입을 확인하여 처리
    retrieved_value = query_params.get("survey_id") # 기본값 없이 가져오기 시도
    st.write(f"DEBUG: query_params.get('survey_id') 결과: {retrieved_value}")
    st.write(f"DEBUG: 결과 타입: {type(retrieved_value)}")
    # st.write(f"DEBUG: 가져온 survey_id_list: {survey_id_list}") # 리스트 내용 확인
    # st.write(f"DEBUG: survey_id_list 타입: {type(survey_id_list)}") # 타입 확인

    final_survey_id = None
    if isinstance(retrieved_value, list) and retrieved_value:
        # 만약 리스트로 반환되는 경우 (예상했던 동작)
        final_survey_id = retrieved_value[0]
        st.write(f"DEBUG: 처리 방식: 리스트에서 ID 추출 ({final_survey_id})")
    elif isinstance(retrieved_value, str) and retrieved_value.strip():
        # 문자열로 직접 반환되는 경우 (현재 확인된 동작)
        final_survey_id = retrieved_value.strip() # 양 끝 공백 제거
        st.write(f"DEBUG: 처리 방식: 문자열에서 직접 ID 할당 ({final_survey_id})")
    else:
        # 그 외 경우 (None, 빈 문자열, 빈 리스트 등)
        st.write(f"DEBUG: 처리 방식: 유효한 survey_id 파라미터 없음 (값: {retrieved_value})")
        final_survey_id = None

    # --- !!! 디버깅: 최종 survey_id 값 확인 !!! ---
    st.write(f"DEBUG: 최종 할당된 final_survey_id: {final_survey_id}")
    st.write(f"DEBUG: final_survey_id 타입: {type(final_survey_id)}")


    # --- 데이터 로드 함수 (디버깅 추가) ---
    # @st.cache_data(ttl=600)
    def load_survey_data(_survey_id):
        st.write(f"DEBUG: load_survey_data 호출됨 (ID: {_survey_id}, 타입: {type(_survey_id)})") # 타입 확인 추가
        # if not supabase or not _survey_id: # UUID는 문자열이므로 이 조건 유효
        # UUID 형식인지 더 엄격하게 체크하려면 정규식 등 사용 가능
        if not supabase or not isinstance(_survey_id, str) or len(_survey_id) < 30: # 간단히 문자열이고 길이가 충분한지 확인
            st.write(f"DEBUG: Supabase 연결 실패 또는 유효하지 않은 survey_id ({_survey_id})")
            return None, None, None

        try:
            # 1. 설문 정보 조회
            st.write(f"DEBUG: surveys 테이블 조회 시도 (ID: {_survey_id})")
            survey_response = supabase.table('surveys') \
                .select("survey_instance_id, survey_name, description, class_id") \
                .eq('survey_instance_id', _survey_id) \
                .single() \
                .execute()
            if not survey_response.data: return None, "설문 정보를 찾을 수 없습니다.", None
            survey_info = survey_response.data
            class_id = survey_info.get('class_id')
            if not class_id: return survey_info, "설문에 연결된 학급 정보를 찾을 수 없습니다.", None
            student_response = supabase.table('students').select("...").eq('class_id', class_id).execute()
            if not student_response.data: return survey_info, "학급의 학생 명단을 찾을 수 없습니다.", None
            students_df = pd.DataFrame(student_response.data)
            st.write("DEBUG: 데이터 로드 성공")
            return survey_info, None, students_df
        except Exception as e:
            st.write(f"DEBUG: 데이터 로딩 중 예외 발생: {e}")
            return None, f"데이터 로딩 중 오류 발생: {e}", None

    # --- 설문 데이터 로드 ---
    survey_info, error_msg, students_df = load_survey_data(final_survey_id)

    # --- 오류 처리 또는 설문 진행 (기존 코드 유지) ---
    if error_msg:
        st.error(error_msg)
    elif not survey_info or students_df is None: # 이 조건이 왜 참이 되는지 디버깅 필요
        st.error("설문 정보를 불러올 수 없습니다. URL을 확인하거나 관리자에게 문의하세요.")
        # 디버깅 정보 추가
        st.write("--- 추가 디버깅 정보 ---")
        st.write(f"load_survey_data 반환값:")
        st.write(f"survey_info: {survey_info}")
        st.write(f"error_msg: {error_msg}")
        st.write(f"students_df is None: {students_df is None}")
        if students_df is not None:
            st.write(f"students_df 내용 (처음 5행):")
            st.dataframe(students_df.head())
    else:
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
                praise_friend = st.text_input("우리 반에서 칭찬하고 싶은 친구는? (없으면 비워두세요)")
                # ... (나머지 필드들) ...
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
                            # ... (나머지 데이터) ...
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
    # st.set_page_config 호출 제거! (이미 위에서 호출함)
    st.info(f"DEBUG: 설문 페이지 렌더링 시작 (survey_id: {survey_id})")

    # --- 데이터 로드 함수 (이전에 pages/_survey_student.py에 있던 내용) ---
    # @st.cache_data(ttl=600) # 캐싱은 필요시 다시 활성화
    def load_survey_data(_survey_id):
        st.write(f"DEBUG: load_survey_data 호출됨 (ID: {_survey_id}, 타입: {type(_survey_id)})")
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
             st.write(f"DEBUG: 데이터 로딩 중 예외 발생: {e}")
             return None, f"데이터 로딩 중 오류 발생: {e}", None

    # --- 설문 데이터 로드 ---
    survey_info, error_msg, students_df = load_survey_data(survey_id)

    if error_msg:
        st.error(error_msg)
    elif not survey_info or students_df is None:
        st.error("설문 정보를 불러올 수 없습니다. URL을 확인하거나 관리자에게 문의하세요.")
    else:
        # --- !!! 여기에 pages/_survey_student.py의 UI 및 제출 로직 전체 삽입 !!! ---
        st.title(f"📝 {survey_info.get('survey_name', '교우관계 설문')}")
        # ... (학생 이름 선택 selectbox) ...
        # ... (관계 매핑 슬라이더 로직) ...
        # ... (추가 질문 form 및 제출 로직) ...
        st.write("학생 설문 페이지 내용 (구현 필요)") # 임시 Placeholder

# --- !!! 메인 교사 페이지 렌더링 함수 !!! ---
def render_home_page():
    # st.set_page_config 호출 제거!
    st.title("🏠 교우관계 분석 시스템")

    if not st.session_state['logged_in']:
        # --- 로그인 폼 ---
        st.subheader("로그인")
        with st.form("login_form"):
            # ... (기존 로그인 폼 코드) ...
            username = st.text_input("사용자 이름 (아이디)")
            password = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("로그인")
            if submitted:
                 check_login(username, password) # check_login 호출
        st.info("관리자에게 계정 생성을 요청하세요.")
    else:
        # --- 로그인 후 환영 메시지 및 로그아웃 버튼 ---
        st.subheader(f"{st.session_state['teacher_name']} 선생님, 안녕하세요!")
        # ... (기존 환영 메시지 코드) ...
        if st.button("로그아웃"):
            logout() # logout 호출

    st.markdown("---")
    st.caption("© 2025 푸른꿈교실. All rights reserved.")


# --- !!! 로그인/로그아웃 함수 (기존 코드) !!! ---
def check_login(username, password):
    # ... (기존 check_login 함수 내용 - 이 파일 안에 있어야 함) ...
    if not supabase: return False
    try:
        response = supabase.table('teachers').select("...").eq('username', username).execute()
        if not response.data: return False
        teacher_data = response.data[0]
        stored_hash = teacher_data.get('password_hash')
        if stored_hash and pwd_context.verify(password, stored_hash):
            st.session_state['logged_in'] = True
            # ... (세션 상태 설정) ...
            st.rerun()
            return True
        else: return False
    except Exception as e: return False

def logout():
    # ... (기존 logout 함수 내용 - 이 파일 안에 있어야 함) ...
    st.session_state['logged_in'] = False
    # ... (세션 상태 초기화) ...
    st.rerun()

# --- !!! 메인 로직: URL 파라미터 확인 후 분기 !!! ---
query_params = st.query_params
final_survey_id = None # final_survey_id 정의 추가
retrieved_value = query_params.get("survey_id") # 단순화된 추출
if isinstance(retrieved_value, list) and retrieved_value: final_survey_id = retrieved_value[0]
elif isinstance(retrieved_value, str) and retrieved_value.strip(): final_survey_id = retrieved_value.strip()

st.write(f"DEBUG: Home.py 에서 확인한 query_params: {query_params}")
st.write(f"DEBUG: Home.py 에서 추출한 survey_id: {final_survey_id}")
st.write(f"DEBUG: Supabase 객체 유효성: {supabase is not None}")

if final_survey_id and supabase: # 최종 추출된 ID 사용
    render_student_survey(final_survey_id)
else:
    render_home_page()