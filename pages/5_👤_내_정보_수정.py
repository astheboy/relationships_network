# pages/5_👤_내_정보_수정.py (구조 예시)
import streamlit as st
from supabase import create_client, Client, PostgrestAPIResponse
from passlib.context import CryptContext
import re # 이메일 형식 검증을 위해 추가
# Home.py와 동일한 Supabase 초기화 및 pwd_context 설정 필요

st.set_page_config(page_title="내 정보 수정", page_icon="👤", layout="centered")

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

# --- 인증 확인 ---
if not st.session_state.get('logged_in'):
    st.warning("로그인이 필요합니다.")
    st.stop()

supabase = init_connection() # Supabase 클라이언트 가져오기
if not supabase: st.stop()
teacher_id = st.session_state.get('teacher_id')
teacher_name = st.session_state.get('teacher_name')

st.title("👤 내 정보 수정")

# 현재 정보 로드 (예시)
try:
    res = supabase.table("teachers").select("username, teacher_name, email").eq("teacher_id", teacher_id).single().execute()
    current_data = res.data if res.data else {}
except Exception as e:
    st.error(f"정보 로드 실패: {e}")
    current_data = {}

st.write(f"**사용자 이름(아이디):** {current_data.get('username', '정보 없음')}")
st.write(f"**교사 이름:** {current_data.get('teacher_name', '정보 없음')}")
st.write(f"**이메일:** {current_data.get('email', '정보 없음')}")

st.divider()

# 이름 변경 폼
with st.form("name_change_form"):
    st.subheader("이름 변경")
    new_teacher_name = st.text_input("새 교사 이름", value=current_data.get('teacher_name', ''))
    name_submitted = st.form_submit_button("이름 변경하기")
    if name_submitted and new_teacher_name:
        try:
            res = supabase.table("teachers").update({"teacher_name": new_teacher_name}).eq("teacher_id", teacher_id).execute()
            if res.data:
                st.session_state['teacher_name'] = new_teacher_name # 세션 상태 업데이트
                st.success("이름이 변경되었습니다.")
                st.rerun()
            else: st.error("이름 변경 실패")
        except Exception as e: st.error(f"오류: {e}")
st.divider() # 구분선 추가

# --- !!! 이메일 변경 폼 추가 !!! ---
with st.form("email_change_form"):
    st.subheader("이메일 변경")
    new_email = st.text_input("새 이메일 주소", value=current_data.get('email', ''))
    password_confirm_email = st.text_input("현재 비밀번호 확인", type="password")
    email_submitted = st.form_submit_button("이메일 변경하기")

    if email_submitted:
        if not new_email or not password_confirm_email:
            st.warning("새 이메일 주소와 현재 비밀번호를 모두 입력해주세요.")
        # 간단한 이메일 형식 검증
        elif not re.match(r"[^@]+@[^@]+\.[^@]+", new_email):
             st.warning("올바른 이메일 형식이 아닙니다.")
        elif new_email == current_data.get('email'):
             st.info("현재 이메일 주소와 동일합니다. 변경할 이메일을 입력하세요.")
        else:
            try:
                # 1. 현재 비밀번호 확인
                pw_res = supabase.table("teachers").select("password_hash").eq("teacher_id", teacher_id).single().execute()
                if not pw_res.data or not pwd_context.verify(password_confirm_email, pw_res.data['password_hash']):
                    st.error("현재 비밀번호가 올바르지 않습니다.")
                else:
                    # 2. 새 이메일 중복 확인 (다른 사용자가 사용하는지)
                    email_check_res = supabase.table("teachers").select("teacher_id").eq("email", new_email).neq("teacher_id", teacher_id).execute()
                    if email_check_res.data:
                        st.error("이미 다른 사용자가 사용 중인 이메일 주소입니다.")
                    else:
                        # 3. 이메일 업데이트 실행
                        update_res = supabase.table("teachers").update({"email": new_email}).eq("teacher_id", teacher_id).execute()
                        if update_res.data or (hasattr(update_res, 'status_code') and update_res.status_code == 204):
                            st.success("이메일 주소가 성공적으로 변경되었습니다.")
                            st.rerun() # 페이지 새로고침하여 변경된 이메일 표시
                        else:
                            st.error(f"이메일 변경 실패: {update_res.error if hasattr(update_res, 'error') else '알 수 없는 오류'}")

            except Exception as e:
                st.error(f"이메일 변경 중 오류 발생: {e}")

st.divider() # 구분선 추가

# 비밀번호 변경 폼
with st.form("password_change_form"):
    st.subheader("비밀번호 변경")
    current_password = st.text_input("현재 비밀번호", type="password")
    new_password = st.text_input("새 비밀번호", type="password")
    new_password_confirm = st.text_input("새 비밀번호 확인", type="password")
    pw_submitted = st.form_submit_button("비밀번호 변경하기")
    if pw_submitted:
        if not all([current_password, new_password, new_password_confirm]):
            st.warning("모든 비밀번호 필드를 입력해주세요.")
        elif new_password != new_password_confirm:
            st.error("새 비밀번호가 일치하지 않습니다.")
        else:
            # --- 현재 비밀번호 확인 로직 ---
            try:
                 res = supabase.table("teachers").select("password_hash").eq("teacher_id", teacher_id).single().execute()
                 if res.data and pwd_context.verify(current_password, res.data['password_hash']):
                      # --- 새 비밀번호 해싱 및 업데이트 ---
                      new_hashed_password = pwd_context.hash(new_password)
                      update_res = supabase.table("teachers").update({"password_hash": new_hashed_password}).eq("teacher_id", teacher_id).execute()
                      if update_res.data:
                           st.success("비밀번호가 성공적으로 변경되었습니다.")
                      else: st.error("비밀번호 변경 실패")
                 else:
                      st.error("현재 비밀번호가 올바르지 않습니다.")
            except Exception as e: st.error(f"비밀번호 변경 중 오류: {e}")

# 이메일 변경 폼 등 추가...