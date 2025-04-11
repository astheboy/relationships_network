# pages/1_🧑‍🏫_학급_관리.py
import streamlit as st
from supabase import Client, PostgrestAPIResponse
import pandas as pd
import os

# --- 페이지 설정 ---
st.set_page_config(page_title="학급 및 학생 관리", page_icon="🧑‍🏫", layout="wide")

# --- Supabase 클라이언트 가져오기 ---
# Home.py에서 초기화된 클라이언트를 직접 가져오는 것은 권장되지 않음.
# 대신, 각 페이지에서 필요시 초기화하거나 공통 모듈 사용.
# 여기서는 간단하게 Home.py의 초기화 함수를 가져와 사용 (실제로는 별도 모듈화 권장)
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
        if url and key:
             st.write("DEBUG: Loaded credentials from environment variables") # 디버깅용
        else:
             st.write("DEBUG: Environment variables not found either.") # 디버깅용


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

# 함수 이름이 같으면 Home.py에 정의된 함수 사용 불가 -> 별도 정의 또는 가져오기 필요
# 여기서는 Home.py와 독립적으로 실행될 수 있도록 재정의
from supabase import create_client # Home.py 에서 가져올 수 있다면 이렇게 사용
# supabase = st.session_state.get('supabase_client') # Home.py 에서 세션에 저장했다면
supabase = init_connection() # 여기서는 다시 초기화

# --- 인증 확인 ---
if not st.session_state.get('logged_in'):
    st.warning("로그인이 필요합니다.")
    st.stop() # 로그인 안되어 있으면 페이지 실행 중지

if not supabase:
    st.error("데이터베이스 연결을 확인해주세요.")
    st.stop()

teacher_id = st.session_state.get('teacher_id')
teacher_name = st.session_state.get('teacher_name', '선생님')

st.title(f"🧑‍🏫 {teacher_name}의 학급 및 학생 관리")
st.write("새로운 학급을 생성하거나 기존 학급의 학생 명단을 관리할 수 있습니다.")

# --- 학급 관리 ---
st.divider()
st.subheader("📚 내 학급 목록")

# 교사의 학급 목록 불러오기
try:
    response: PostgrestAPIResponse = supabase.table('classes') \
        .select("class_id, class_name, description") \
        .eq('teacher_id', teacher_id) \
        .order('created_at', desc=False) \
        .execute()

    if response.data:
        classes = response.data
        class_options = {c['class_name']: c['class_id'] for c in classes} # 이름:ID 딕셔너리
        selected_class_name = st.selectbox(
            "관리할 학급을 선택하세요:",
            options=class_options.keys(),
            index=None, # 기본 선택 없음
            placeholder="학급 선택..."
        )
        selected_class_id = class_options.get(selected_class_name) if selected_class_name else None

        # 선택된 학급 정보 표시 (선택 사항)
        if selected_class_name:
             selected_class_info = next((c for c in classes if c['class_id'] == selected_class_id), None)
             if selected_class_info and selected_class_info.get('description'):
                 st.caption(f"학급 설명: {selected_class_info['description']}")

    else:
        st.info("아직 생성된 학급이 없습니다. 새 학급을 만들어 보세요.")
        classes = []
        selected_class_id = None

except Exception as e:
    st.error(f"학급 목록을 불러오는 중 오류 발생: {e}")
    selected_class_id = None # 오류 시 선택 불가

# 새 학급 생성 폼
with st.expander("➕ 새 학급 생성"):
    with st.form("new_class_form", clear_on_submit=True):
        new_class_name = st.text_input("새 학급 이름 (예: 3학년 희망반)", max_chars=50)
        new_class_desc = st.text_area("학급 설명 (선택 사항)", max_chars=200)
        submitted = st.form_submit_button("생성하기")

        if submitted:
            if not new_class_name:
                st.warning("학급 이름을 입력해주세요.")
            else:
                try:
                    response: PostgrestAPIResponse = supabase.table('classes').insert({
                        'teacher_id': teacher_id,
                        'class_name': new_class_name,
                        'description': new_class_desc
                    }).execute()

                    if response.data:
                        st.success(f"'{new_class_name}' 학급이 생성되었습니다!")
                        st.rerun() # 학급 목록 갱신을 위해 새로고침
                    else:
                        # Supabase 응답 구조 변경 가능성 고려 (오류 메시지 확인 필요)
                        st.error("학급 생성 중 오류가 발생했습니다.")
                        print("Supabase insert response:", response) # 디버깅용

                except Exception as e:
                    st.error(f"학급 생성 중 오류 발생: {e}")

# --- 학생 명단 관리 (다음 단계에서 구현) ---
st.divider()
st.subheader("🧑‍🎓 학생 명단 관리")

if selected_class_id:
    st.write(f"**'{selected_class_name}'** 학급의 학생 명단입니다.")

    # 학생 목록 불러오기 함수
    def get_students(class_id):
        try:
            response = supabase.table('students') \
                .select("student_id, student_name") \
                .eq('class_id', class_id) \
                .order('student_name', desc=False) \
                .execute()
            return pd.DataFrame(response.data) if response.data else pd.DataFrame(columns=['student_id', 'student_name'])
        except Exception as e:
            st.error(f"학생 목록 조회 중 오류 발생: {e}")
            return pd.DataFrame(columns=['student_id', 'student_name'])

    # 초기 학생 데이터 로드
    student_df = get_students(selected_class_id)

    # --- 학생 추가 (개별) ---
    with st.form("new_student_form", clear_on_submit=True):
        new_student_name = st.text_input("추가할 학생 이름")
        submitted = st.form_submit_button("학생 추가")
        if submitted and new_student_name:
            try:
                # 중복 이름 체크 (선택 사항)
                existing_names = student_df['student_name'].tolist()
                if new_student_name in existing_names:
                    st.warning(f"이미 '{new_student_name}' 학생이 존재합니다.")
                else:
                    response = supabase.table('students').insert({
                        'class_id': selected_class_id,
                        'student_name': new_student_name
                    }).execute()
                    if response.data:
                        st.success(f"'{new_student_name}' 학생이 추가되었습니다.")
                        st.rerun() # 데이터 갱신
                    else:
                        st.error("학생 추가 중 오류 발생")
            except Exception as e:
                st.error(f"학생 추가 중 오류 발생: {e}")
        elif submitted and not new_student_name:
            st.warning("학생 이름을 입력해주세요.")

    # --- 학생 명단 업로드 (CSV/Excel) ---
    uploaded_file = st.file_uploader("학생 명단 파일 업로드 (CSV 또는 Excel)", type=["csv", "xlsx"])
    if uploaded_file is not None:
        try:
            # 파일 확장자에 따라 읽기
            if uploaded_file.name.endswith('.csv'):
                # CSV 파일 인코딩 주의 (utf-8 또는 cp949/euc-kr 등)
                try:
                    new_students_df = pd.read_csv(uploaded_file)
                except UnicodeDecodeError:
                    # UTF-8 실패 시 다른 인코딩 시도
                    uploaded_file.seek(0) # 파일 포인터 초기화
                    new_students_df = pd.read_csv(uploaded_file, encoding='cp949') # 또는 'euc-kr'
            elif uploaded_file.name.endswith('.xlsx'):
                new_students_df = pd.read_excel(uploaded_file)
            else:
                st.error("지원하지 않는 파일 형식입니다.")
                new_students_df = None

            if new_students_df is not None:
                # 파일에서 학생 이름 컬럼 추출 (첫 번째 컬럼으로 가정)
                # 또는 특정 컬럼명 지정 (예: new_students_df['학생 이름'])
                if not new_students_df.empty:
                    student_name_col = new_students_df.columns[0]
                    new_student_names = new_students_df[student_name_col].astype(str).str.strip().tolist()
                    new_student_names = [name for name in new_student_names if name] # 빈 이름 제거

                    # DB에 삽입할 데이터 준비 (중복 제외)
                    existing_names = student_df['student_name'].tolist()
                    students_to_insert = []
                    skipped_count = 0
                    for name in new_student_names:
                        if name not in existing_names:
                            students_to_insert.append({
                                'class_id': selected_class_id,
                                'student_name': name
                            })
                        else:
                            skipped_count += 1

                    # 데이터 삽입 실행
                    if students_to_insert:
                        response = supabase.table('students').insert(students_to_insert).execute()
                        if response.data:
                            st.success(f"{len(students_to_insert)}명의 학생이 성공적으로 추가되었습니다.")
                            if skipped_count > 0:
                                st.info(f"{skipped_count}명의 학생은 이미 존재하여 건너뛰었습니다.")
                            st.rerun() # 데이터 갱신
                        else:
                            st.error("학생 명단 업로드 중 오류 발생")
                    elif skipped_count > 0:
                         st.info(f"업로드한 파일의 모든 학생({skipped_count}명)이 이미 명단에 존재합니다.")
                    else:
                         st.warning("업로드할 새로운 학생이 없습니다.")

                else:
                    st.warning("업로드한 파일에 학생 데이터가 없습니다.")

        except Exception as e:
            st.error(f"파일 처리 중 오류 발생: {e}")

    # --- 학생 목록 표시 및 수정/삭제 (st.data_editor 사용) ---
    st.write("학생 목록 (이름 수정 또는 행 삭제 가능):")

    # 원본 데이터 복사 (변경 감지용)
    edited_df = student_df.copy()

    edited_df = st.data_editor(
        student_df,
        key="student_editor",
        column_config={
            "student_id": None, # ID 컬럼 숨김
            "student_name": st.column_config.TextColumn(
                "학생 이름",
                help="학생 이름을 수정할 수 있습니다.",
                required=True,
            )
        },
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic" # 행 추가/삭제 활성화
    )

    # 변경 사항 감지 및 처리
    if not student_df.equals(edited_df):
        st.info("변경 사항을 감지했습니다. 저장 버튼을 눌러 반영하세요.")

        if st.button("변경 사항 저장"):
            try:
                # 변경된 행 찾기 (Update)
                diff = pd.concat([student_df, edited_df]).drop_duplicates(keep=False)
                updates = []
                original_ids_in_diff = set(diff[diff['student_id'].isin(student_df['student_id'])]['student_id'])

                for index, row in edited_df.iterrows():
                    student_id = row['student_id']
                    if student_id in original_ids_in_diff: # 수정된 행
                         # student_id가 None이거나 비어있지 않은지 확인 후 업데이트 리스트에 추가
                         if student_id and pd.notna(student_id):
                              updates.append({'student_id': student_id, 'student_name': row['student_name']})

                if updates:
                     # Supabase는 기본적으로 upsert 사용 가능, 여기서는 update 사용 예시
                     # update는 리스트 직접 전달 불가, 개별 실행 필요 또는 함수형 언어 활용
                     update_errors = 0
                     for update_data in updates:
                         try:
                              response = supabase.table('students') \
                                         .update({'student_name': update_data['student_name']}) \
                                         .eq('student_id', update_data['student_id']) \
                                         .execute()
                              if not response.data and not hasattr(response, 'status_code') and response.status_code != 204: # 성공 시 보통 data 없음, 상태코드 확인 필요
                                   print(f"Update failed for {update_data['student_id']}: {response}") # 실패 로깅
                                   update_errors += 1
                         except Exception as update_e:
                              print(f"Update exception for {update_data['student_id']}: {update_e}")
                              update_errors += 1
                     if update_errors == 0:
                          st.success(f"{len(updates)}명의 학생 정보가 수정되었습니다.")
                     else:
                          st.error(f"{update_errors}건의 학생 정보 수정 중 오류 발생.")


                # 삭제된 행 찾기 (Delete)
                deleted_ids = list(set(student_df['student_id']) - set(edited_df['student_id']))
                if deleted_ids:
                    # NaN 값 제거 (혹시 모를 경우 대비)
                    deleted_ids = [id_ for id_ in deleted_ids if pd.notna(id_)]
                    if deleted_ids: # 유효한 ID가 있을 때만 실행
                         delete_errors = 0
                         try:
                              # in_ 연산자로 한 번에 삭제 시도
                              response = supabase.table('students') \
                                         .delete() \
                                         .in_('student_id', deleted_ids) \
                                         .execute()
                              # 삭제 성공 여부 확인 (API 응답 구조에 따라 다를 수 있음)
                              # 성공 시 보통 data가 비어있거나, 삭제된 row 수 반환 가능
                              # 여기서는 간단히 성공 메시지만 표시
                              st.success(f"{len(deleted_ids)}명의 학생 정보가 삭제되었습니다.")
                         except Exception as delete_e:
                              st.error(f"학생 정보 삭제 중 오류 발생: {delete_e}")


                # 추가된 행 찾기 (Add) - data_editor에서 num_rows="dynamic" 사용 시
                added_rows = edited_df[~edited_df['student_id'].isin(student_df['student_id'])]
                inserts = []
                for index, row in added_rows.iterrows():
                     if pd.notna(row['student_name']) and row['student_name'].strip(): # 이름이 있고 비어있지 않은 경우
                          inserts.append({
                              'class_id': selected_class_id,
                              'student_name': row['student_name'].strip()
                          })

                if inserts:
                     response = supabase.table('students').insert(inserts).execute()
                     if response.data:
                         st.success(f"{len(inserts)}명의 학생이 추가되었습니다.")
                     else:
                         st.error(f"{len(inserts)}건의 학생 추가 중 오류 발생")

                # 모든 작업 후 새로고침
                st.rerun()

            except Exception as e:
                st.error(f"변경 사항 저장 중 오류 발생: {e}")

else:
    st.info("학생 명단을 관리하려면 먼저 위에서 학급을 선택하거나 생성해주세요.")
