import google.generativeai as genai
import traceback

def call_gemini(prompt, api_key):
    """Gemini API를 호출하고 결과를 반환하는 함수"""
    if not api_key:
        return "오류: API 키가 설정되지 않았습니다."
    try:
        # 함수 호출 시마다 API 키로 클라이언트 설정
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-2.0-flash-lite') # 사용할 모델 선택

        # API 호출 (안전 설정 등 추가 가능)
        response = model.generate_content(prompt)

        # 결과 텍스트 추출 (오류/안전 블록 처리 포함)
        if response.parts:
            return response.text
        elif response.prompt_feedback.block_reason:
             block_reason = response.prompt_feedback.block_reason
             print(f"Gemini content blocked. Reason: {block_reason}")
             return f"오류: 콘텐츠 생성 차단됨 (이유: {block_reason}). 프롬프트를 수정하거나 안전 설정을 확인하세요."
        else:
             # 예상치 못한 빈 응답
             print("Gemini response missing parts and block reason:", response)
             return "오류: AI로부터 유효한 응답을 받지 못했습니다."

    except Exception as e:
        # 상세 오류 로깅
        print(f"Gemini API 호출 중 오류 발생: {e}")
        traceback.print_exc() # 전체 traceback 출력 (콘솔 확인용)
        # 사용자에게 보여줄 일반적인 오류 메시지
        error_message = f"AI 분석 중 오류 발생: {type(e).__name__}"
        if "API key not valid" in str(e):
             error_message = "오류: 설정된 Gemini API 키가 유효하지 않습니다. 설정 페이지를 확인하세요."
        elif "quota" in str(e).lower():
             error_message = "오류: API 사용 할당량을 초과했을 수 있습니다."
        return error_message