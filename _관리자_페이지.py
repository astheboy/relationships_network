# pages/_9_👑_관리자_페이지.py
import streamlit as st
from supabase import Client, PostgrestAPIResponse

# --- 페이지 설정 ---
st.set_page_config(page_title="관리자 대시보드", page_icon="👑", layout="wide")

# --- Supabase 클라이언트 가져오기 ---
@st.cache_resource
def init_connection():
    # ... (이전과 동일한 Supabase 클라이언트 초기화 함수) ...
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"] # 관리자 작업은 service_key 필요 가능성 있음
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase 연결 오류: {e}")
        return None

from supabase import create_client
supabase = init_connection()

# --- 관리자 인증 및 권한 확인 ---
is_admin = False
if not st.session_state.get('logged_in'):
    st.warning("👑 관리자 로그인이 필요합니다.")
    st.info("Home 페이지로 이동하여 관리자 계정으로 로그인해주세요.")
    st.stop()
elif not supabase:
    st.error("데이터베이스 연결을 확인해주세요.")
    st.stop()
else:
    teacher_id = st.session_state.get('teacher_id')
    try:
        # 현재 로그인한 사용자의 is_admin 플래그 확인
        response = supabase.table("teachers") \
            .select("is_admin") \
            .eq("teacher_id", teacher_id) \
            .single() \
            .execute()
        if response.data and response.data.get('is_admin') is True:
            is_admin = True
        else:
            st.error("🚫 접근 권한이 없습니다. 관리자 계정으로 로그인하세요.")
            st.stop()
    except Exception as e:
        st.error(f"권한 확인 중 오류 발생: {e}")
        st.stop()

# --- 관리자 대시보드 내용 ---
st.title("👑 관리자 대시보드")
st.write("애플리케이션 전체 사용 현황 통계입니다.")
st.divider()

# --- 통계 데이터 조회 ---
try:
    # Supabase의 count 기능을 사용하여 효율적으로 개수 조회
    teachers_count = supabase.table('teachers').select('*', count='exact').execute().count
    classes_count = supabase.table('classes').select('*', count='exact').execute().count
    students_count = supabase.table('students').select('*', count='exact').execute().count
    surveys_count = supabase.table('surveys').select('*', count='exact').execute().count
    active_surveys_count = supabase.table('surveys').select('*', count='exact').eq('status', '진행중').execute().count
    responses_count = supabase.table('survey_responses').select('*', count='exact').execute().count

    # --- 통계 표시 ---
    st.subheader("📊 주요 통계")
    col1, col2, col3 = st.columns(3)
    col1.metric("총 교사 수", f"{teachers_count} 명")
    col2.metric("총 개설 학급 수", f"{classes_count} 개")
    col3.metric("총 등록 학생 수", f"{students_count} 명")

    col4, col5, col6 = st.columns(3)
    col4.metric("총 설문 회차 수", f"{surveys_count} 회")
    col5.metric("진행중인 설문 수", f"{active_surveys_count} 회")
    col6.metric("총 설문 응답 수", f"{responses_count} 건")

    # 여기에 추가적인 통계나 관리 기능(사용자 목록 등)을 넣을 수 있습니다.
    st.divider()
    st.info("향후 사용자 관리(추가/수정/삭제), 상세 통계 등의 기능이 추가될 수 있습니다.")

except Exception as e:
    st.error(f"통계 데이터 조회 중 오류 발생: {e}")