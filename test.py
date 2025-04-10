# create_test_teacher.py (별도 파일로 실행)
from supabase import create_client, Client
from passlib.context import CryptContext
from dotenv import load_dotenv # .env 파일 사용 시
import os

# .env 파일에서 환경 변수 로드 (선택 사항)
load_dotenv()

# Supabase 정보 (환경 변수 또는 직접 입력)
SUPABASE_URL = "https://mlrztwlyvmoazwbmtivm.supabase.co" # 또는 "YOUR_SUPABASE_URL"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1scnp0d2x5dm1vYXp3Ym10aXZtIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDQxODg1MzUsImV4cCI6MjA1OTc2NDUzNX0.07s3qQBf7n7wao4WahJwtpntoXo9FFGOrinayF2GrFU" # 또는 "YOUR_SUPABASE_ANON_KEY"
# 주의: 데이터를 삽입/수정하려면 일반적으로 service_role 키가 필요할 수 있습니다.
# 여기서는 anon 키로 시도하고, 권한 오류 발생 시 service_role 키 사용 필요.
# 또는 Supabase RLS 정책에서 teachers 테이블에 대한 INSERT를 허용해야 합니다.
# service_role 키를 사용한다면 더 안전하게 관리해야 합니다.
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") # 서비스 키 사용 권장

# 비밀번호 해싱 설정
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# 테스트 교사 정보
test_username = "teacher_test"
test_password = "password123" # 실제 사용할 비밀번호
test_teacher_name = "테스트교사"

# 비밀번호 해싱
hashed_password = pwd_context.hash(test_password)

try:
    # 서비스 키로 클라이언트 생성 (쓰기 권한)
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) # anon 키
    # supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY) # 서비스 키 권장

    # 데이터 삽입
    data, count = supabase.table('teachers').insert({
        'username': test_username,
        'password_hash': hashed_password,
        'teacher_name': test_teacher_name
        # email 등 다른 필드 추가 가능
    }).execute()

    print("테스트 교사 데이터 삽입 완료!")
    # print("삽입 결과:", data, count) # 결과 확인 (디버깅용)

except Exception as e:
    print(f"테스트 교사 데이터 삽입 중 오류 발생: {e}")