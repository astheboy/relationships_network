# pages/2_🔗_설문_관리.py
import streamlit as st
from supabase import Client, PostgrestAPIResponse
import pandas as pd
from urllib.parse import urlencode # URL 파라미터 생성을 위해 추가

# --- 페이지 설정 ---
st.set_page_config(page_title="설문 관리", page_icon="🔗", layout="wide")

# --- Supabase 클라이언트 가져오기 ---
@st.cache_resource
def init_connection():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase 연결 중 오류 발생: {e}")
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

st.title(f"🔗 {teacher_name}의 설문 관리")
st.write("학급을 선택하고 설문 회차를 생성하거나 기존 설문의 링크를 확인할 수 있습니다.")

# --- 학급 선택 ---
st.divider()
st.subheader("1. 설문 대상 학급 선택")

try:
    class_response: PostgrestAPIResponse = supabase.table('classes') \
        .select("class_id, class_name") \
        .eq('teacher_id', teacher_id) \
        .order('created_at', desc=False) \
        .execute()

    if class_response.data:
        classes = class_response.data
        class_options = {c['class_name']: c['class_id'] for c in classes}
        selected_class_name = st.selectbox(
            "설문을 진행할 학급을 선택하세요:",
            options=class_options.keys(),
            index=None,
            placeholder="학급 선택..."
        )
        selected_class_id = class_options.get(selected_class_name)
    else:
        st.info("먼저 '학급 및 학생 관리' 메뉴에서 학급을 생성해주세요.")
        selected_class_id = None

except Exception as e:
    st.error(f"학급 목록을 불러오는 중 오류 발생: {e}")
    selected_class_id = None

# --- 설문 회차 관리 ---
if selected_class_id:
    st.divider()
    st.subheader(f"2. '{selected_class_name}' 학급 설문 회차 관리")

    # 기존 설문 회차 목록 조회 함수
    def get_surveys(class_id):
        try:
            response = supabase.table('surveys') \
                .select("survey_instance_id, survey_name, description, status, created_at") \
                .eq('class_id', class_id) \
                .order('created_at', desc=True) \
                .execute()
            return pd.DataFrame(response.data) if response.data else pd.DataFrame()
        except Exception as e:
            st.error(f"설문 목록 조회 중 오류 발생: {e}")
            return pd.DataFrame()

    survey_df = get_surveys(selected_class_id)

    if not survey_df.empty:
        st.write("기존 설문 목록:")

        # --- 데이터 전처리 (st.data_editor 호출 전) ---
        processed_df = survey_df.copy() # 원본 복사

        # 1. status 컬럼 처리: None 값을 기본값('준비중')으로 채우고, 문자열로 변환
        status_options = ['준비중', '진행중', '완료']
        processed_df['status'] = processed_df['status'].fillna('준비중').astype(str)
        # 혹시 모를 options 외 값 처리 (선택적: 첫번째 옵션 값으로 강제 변환 등)
        processed_df['status'] = processed_df['status'].apply(lambda x: x if x in status_options else status_options[0])


        # 2. created_at 컬럼 처리: datetime 객체로 변환, NaT 처리
        processed_df['created_at'] = pd.to_datetime(processed_df['created_at'], errors='coerce') # 변환 안되면 NaT

        # 3. survey_name, description 컬럼 처리: 문자열 변환 및 None 값 처리
        processed_df['survey_name'] = processed_df['survey_name'].fillna('').astype(str)
        processed_df['description'] = processed_df['description'].fillna('').astype(str)

        # (디버깅용) 전처리 후 DataFrame 정보 출력
        # st.write("전처리 후 데이터 타입:")
        # st.dataframe(processed_df.dtypes.astype(str))
        # st.write("전처리 후 데이터 샘플:")
        # st.dataframe(processed_df.head())
        # -----------------------------------------

        edited_survey_df = st.data_editor(
             processed_df, # 전처리된 DataFrame 사용
             column_config={
                  "survey_instance_id": None, # ID 숨김
                  "survey_name": st.column_config.TextColumn("설문 이름", width="medium"),
                  "description": st.column_config.TextColumn("설명", width="large"),
                  "status": st.column_config.SelectboxColumn(
                       "상태", options=status_options, width="small", required=True), # required=True 추가 고려
                  "created_at": st.column_config.DatetimeColumn(
                      "생성일",
                      format="YYYY-MM-DD HH:mm", # 표시 형식
                      # step=60*60 # 1시간 단위 (선택 사항)
                  )
             },
             hide_index=True,
             use_container_width=True,
             key="survey_editor"
        )

        # 설문 상태 변경 저장 버튼 (data_editor 변경 시)
        if not processed_df[['status']].equals(edited_survey_df[['status']]): # 상태 변경만 감지 (다른 컬럼도 편집 가능하게 하려면 로직 수정 필요)
             if st.button("설문 상태 변경 저장"):
                  try:
                      update_errors = 0
                      for index, row in edited_survey_df.iterrows():
                          original_row = processed_df.loc[index] # loc 사용 권장
                          if row['status'] != original_row['status']:
                               response = supabase.table('surveys') \
                                          .update({'status': row['status']}) \
                                          .eq('survey_instance_id', row['survey_instance_id']) \
                                          .execute()
                               # 응답 확인 로직 강화 필요 (예: response.error 확인)
                               # if response.error: update_errors += 1
                      if update_errors == 0:
                           st.success("설문 상태가 업데이트되었습니다.")
                           st.rerun()
                      else:
                           st.error("일부 설문 상태 업데이트 중 오류 발생.")
                  except Exception as e:
                       st.error(f"상태 업데이트 중 오류: {e}")

        st.write("---") # 구분선
        st.write("📋 설문 링크 확인:")
        # 설문 선택 (링크 생성용)
        link_survey_options = {s['survey_name']: s['survey_instance_id'] for i, s in survey_df.iterrows()}
        selected_survey_name_for_link = st.selectbox(
             "링크를 확인할 설문을 선택하세요:", options=link_survey_options.keys())

        if selected_survey_name_for_link:
             selected_survey_id_for_link = link_survey_options[selected_survey_name_for_link]
             # 앱의 기본 URL 가져오기 (배포 환경에 따라 조정 필요)
             # 로컬 개발 시: http://localhost:8501
             # Streamlit Cloud 등: 해당 앱 URL
             # 여기서는 상대 경로 사용 (같은 앱 내 페이지 이동)
             query_params = urlencode({'page': 'survey_student', 'survey_id': selected_survey_id_for_link})
             # survey_url = f"/survey_student?{query_params}" # Streamlit 내부 페이지 이동 시
             # 또는 전체 URL 구성:
             app_base_url = st.get_option('server.baseUrlPath') # 기본값 '/'
             # Streamlit Cloud 등 실제 URL 구성 방식은 다를 수 있음
             # 여기서는 현재 URL 기반으로 단순하게 구성 시도
             # 주의: 이 방식은 로컬/배포 환경에 따라 정확하지 않을 수 있음
             current_url = "http://localhost:8501" # 기본 로컬 주소 (실제 환경 맞게 수정 필요)
             survey_url = f"{current_url}/survey_student?{query_params}"


             st.write(f"**'{selected_survey_name_for_link}' 설문 링크:**")
             st.code(survey_url)
             st.caption("이 링크를 복사하여 학생들에게 공유하세요.")
             # st.link_button("설문 페이지 미리보기", survey_url) # 버튼 형태 링크

    else:
        st.info("아직 생성된 설문이 없습니다.")

    # 새 설문 회차 생성 폼
    with st.expander("➕ 새 설문 회차 생성"):
        with st.form("new_survey_form", clear_on_submit=True):
            new_survey_name = st.text_input("새 설문 이름 (예: 2025년 1학기 교우관계)", max_chars=100)
            new_survey_desc = st.text_area("설명 (선택 사항)", max_chars=300)
            new_survey_status = st.selectbox("상태", options=['준비중', '진행중', '완료'], index=1) # 기본값 '진행중'
            submitted = st.form_submit_button("설문 생성하기")

            if submitted:
                if not new_survey_name:
                    st.warning("설문 이름을 입력해주세요.")
                else:
                    try:
                        response: PostgrestAPIResponse = supabase.table('surveys').insert({
                            'class_id': selected_class_id,
                            'teacher_id': teacher_id,
                            'survey_name': new_survey_name,
                            'description': new_survey_desc,
                            'status': new_survey_status
                        }).execute()

                        if response.data:
                            st.success(f"'{new_survey_name}' 설문이 생성되었습니다!")
                            st.rerun() # 목록 갱신
                        else:
                            st.error("설문 생성 중 오류 발생")
                            print("Supabase survey insert response:", response)

                    except Exception as e:
                        st.error(f"설문 생성 중 오류 발생: {e}")

else:
    st.info("먼저 학급을 선택해주세요.")