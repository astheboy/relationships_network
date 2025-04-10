# pages/4_⚙️_설정.py
import streamlit as st

# --- 페이지 설정 ---
st.set_page_config(page_title="설정", page_icon="⚙️", layout="centered")

# --- 인증 확인 ---
# Home.py 또는 공통 모듈에서 세션 상태 확인
# 이 페이지는 로그인된 사용자만 접근 가능해야 함
if not st.session_state.get('logged_in'):
    st.warning("⚙️ 이 페이지에 접근하려면 먼저 로그인이 필요합니다.")
    st.info("Home 페이지로 이동하여 로그인해주세요.")
    st.stop() # 로그인 안되어 있으면 페이지 실행 중지

teacher_name = st.session_state.get('teacher_name', '선생님')
st.title(f"⚙️ {teacher_name} 설정")
st.write("애플리케이션의 추가 기능 사용을 위한 설정을 관리합니다.")
st.divider()

# --- Gemini API 키 설정 ---
st.subheader("✨ 생성형 AI 분석 설정 (Gemini)")
st.markdown("""
분석 대시보드의 서술형 응답에 대한 AI 요약 및 심층 분석 기능을 사용하려면 Google Gemini API 키가 필요합니다.
API 키는 [Google AI Studio](https://aistudio.google.com/app/apikey)에서 무료로 발급받을 수 있습니다.
입력된 키는 **현재 브라우저 세션 동안에만 임시로 저장**되며, 창을 닫거나 로그아웃하면 다시 입력해야 합니다.
""")

# 현재 세션에 저장된 키 가져오기 (없으면 None)
current_api_key = st.session_state.get('gemini_api_key', None)

# 상태 표시
if current_api_key:
    # 실제 키를 그대로 보여주지 않도록 일부만 마스킹 처리
    masked_key = current_api_key[:4] + "****" + current_api_key[-4:]
    st.success(f"✅ 현재 세션에 API 키가 저장되어 있습니다: `{masked_key}`")
else:
    st.warning("⚠️ 현재 세션에 Gemini API 키가 설정되지 않았습니다. AI 분석 기능을 사용하려면 키를 입력해주세요.")

# API 키 입력 폼
with st.form("api_key_form"):
    api_key_input = st.text_input(
        "Gemini API 키 입력",
        type="password",
        placeholder="발급받은 API 키를 여기에 붙여넣으세요.",
        help="입력된 키는 현재 세션에만 저장됩니다."
    )
    submitted = st.form_submit_button("API 키 저장 (현재 세션)")

    if submitted:
        if api_key_input and len(api_key_input) > 10: # 간단한 유효성 검사 (길이)
            st.session_state['gemini_api_key'] = api_key_input
            st.success("✅ API 키가 현재 세션에 성공적으로 저장되었습니다!")
            st.rerun() # 상태 표시 업데이트를 위해 새로고침
        elif api_key_input:
             st.error("유효한 API 키 형식이 아닌 것 같습니다. 다시 확인해주세요.")
        else:
            st.warning("API 키를 입력해주세요.")

# API 키 제거 버튼 (선택 사항)
if current_api_key:
    if st.button("현재 세션에서 API 키 제거"):
        if 'gemini_api_key' in st.session_state:
            del st.session_state['gemini_api_key']
        st.info("현재 세션에서 API 키가 제거되었습니다.")
        st.rerun() # 상태 표시 업데이트