# Home.py
import streamlit as st
from supabase import create_client, Client, PostgrestAPIResponse # PostgrestAPIResponse 추가
from passlib.context import CryptContext # 비밀번호 해싱용
import time # 로그인 시 잠시 딜레이를 주기 위함 (선택 사항)

# --- 페이지 설정 (가장 먼저) ---
st.set_page_config(page_title="교우관계 분석 시스템", page_icon="🏠", layout="wide")

# 비밀번호 해싱 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Supabase 클라이언트 초기화 함수
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase 연결 중 오류 발생: {e}")
        return None

supabase = init_connection()

# --- 세션 상태 초기화 ---
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'teacher_id' not in st.session_state:
    st.session_state['teacher_id'] = None
if 'teacher_name' not in st.session_state:
    st.session_state['teacher_name'] = None

# --- 로그인/로그아웃 처리 함수 ---
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

# --- 앱 메인 UI ---
st.title("🏠 교우관계 분석 시스템")

if not st.session_state['logged_in']:
    # --- 로그인 폼 ---
    st.subheader("로그인")
    with st.form("login_form"):
        username = st.text_input("사용자 이름 (아이디)")
        password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("로그인")

        if submitted:
            if not username or not password:
                st.warning("사용자 이름과 비밀번호를 모두 입력해주세요.")
            else:
                check_login(username, password)
    st.info("관리자에게 계정 생성을 요청하세요.") # 회원가입 기능 대신 안내 문구

else:
    # --- 로그인 후 환영 메시지 및 로그아웃 버튼 ---
    st.subheader(f"{st.session_state['teacher_name']} 선생님, 안녕하세요!")
    st.write("왼쪽 사이드바 메뉴를 통해 학급 관리, 설문 관리, 분석 대시보드 등의 기능을 이용할 수 있습니다.")

    if st.button("로그아웃"):
        logout()

# 페이지 푸터 (선택 사항)
st.markdown("---")
st.caption("© 2025 푸른꿈교실. All rights reserved.")