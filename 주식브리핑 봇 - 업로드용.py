import os
import platform
import shutil
import time
import warnings
import requests
import yfinance as yf
from google import genai

# 윈도우 환경 한글 경로 SSL 인증서 오류 자동 방지 (리눅스/깃허브에서는 자동 건너뜀)
if platform.system() == "Windows":
    try:
        import certifi
        public_cert = r"C:\Users\Public\cacert.pem"
        shutil.copyfile(certifi.where(), public_cert)
        os.environ["CURL_CA_BUNDLE"] = public_cert
        os.environ["SSL_CERT_FILE"] = public_cert
    except Exception:
        pass

warnings.filterwarnings("ignore")

# =========================================================
# 1. API 키 및 기본 설정
# =========================================================
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY"
TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

client = genai.Client(api_key=GEMINI_API_KEY)

# 모니터링 티커 설정 (기존 보유 + 나스닥 지수 + 단기 기회 포착용 빅테크/반도체)
tickers = ["QLD", "JEPQ", "NVDA", "GOOGL", "AIPO",]

# =========================================================
# 2. 주가 데이터 수집 (애프터/프리마켓 1분 단위 반영)
# =========================================================
print("1/3. 📊 최신 주가(장외 반영)를 수집 중입니다...")
price_data = ""

name_map = {
    "QLD": "QLD (나스닥 2배)",
    "JEPQ": "JEPQ (나스닥 커버드콜)",
    "NVDA": "엔비디아(NVDA)",
    "GOOGL": "알파벳A(GOOGL)",
    "AIPO": "AI 전력인프라 ETF(AIPO)",
}

for ticker in tickers:
    stock = yf.Ticker(ticker)
    df = stock.history(period="1d", interval="1m", prepost=True)
    display_name = name_map.get(ticker, ticker)
    
    if not df.empty:
        latest_price = df['Close'].iloc[-1]
        price_data += f"- {display_name}: ${latest_price:.2f}\n"
    else:
        fallback_price = stock.fast_info.get('last_price', 0)
        price_data += f"- {display_name}: ${fallback_price:.2f}\n"

print("\n[수집된 주가 데이터]")
print(price_data)

# =========================================================
# 3. 구글 AI 맞춤 분석 요청 (gemini-3.8-flash 집중 재시도 + 자동 모델 탐색)
# =========================================================
print("2/3. 🤖 AI가 님 맞춤 투자 브리핑을 작성 중입니다...")

prompt = f"""
너는 월스트리트 최고의 시니어 투자 애널리스트야. 
오늘 아침 에게 전달할 투자 브리핑을 작성해야 해.

[고객 정보]
- 이름: 

[현재 보유 자산 및 예수금]
- 보유 현금 및 달러
- 보유중인 주식 및 ETF

[실시간 수집 주가 (장외/프리마켓 반영)]
{price_data}

[작성 지침 - 필수 반영]
1. 
2.
3.
4.
5.


ai_report = ""

# 1단계: 검증된 gemini-3.8-flash로 최대 5회 재시도
for attempt in range(5):
    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )
        ai_report = response.text
        break
    except Exception as e:
        error_msg = str(e)
        if "503" in error_msg or "UNAVAILABLE" in error_msg or "429" in error_msg:
            wait_time = (attempt + 1) * 10
            print(f"    ⚠️ [gemini-3.8-flash] 서버 지연 중. {wait_time}초 후 재시도... ({attempt+1}/5)")
            time.sleep(wait_time)
        else:
            print(f"    ⚠️ 호출 오류 발생: {error_msg[:60]}...")
            break

# 2단계: 5번 모두 서버 혼잡으로 실패 시, 내 키로 사용 가능한 다른 Gemini 모델 자동 탐색 후 실행
if not ai_report:
    print("    🔄 다른 사용 가능한 AI 모델을 자동으로 탐색합니다...")
    try:
        for m in client.models.list():
            m_name = m.name.replace("models/", "")
            if "gemini" in m_name and "3.8-flash" not in m_name and "embedding" not in m_name and "image" not in m_name and "audio" not in m_name:
                try:
                    print(f"    ➡️ 대체 모델 [{m_name}] 시도 중...")
                    response = client.models.generate_content(
                        model=m_name,
                        contents=prompt
                    )
                    ai_report = response.text
                    print(f"    ✅ [{m_name}] 모델로 브리핑 생성 성공!")
                    break
                except Exception:
                    continue
    except Exception as e:
        print(f"    ⚠️ 모델 목록 조회 실패: {e}")

if not ai_report:
    ai_report = "⚠️ 현재 구글 AI 전체 서버에 일시적 과부하가 발생하여 시황 분석을 불러오지 못했습니다.\n\n[수집된 현재가]\n" + price_data
# =========================================================
# 4. 텔레그램 메시지 전송 (에러 상세 출력 포함)
# =========================================================
print("3/3. 📱 텔레그램으로 브리핑을 전송합니다...")

# 별표(**) 등 마크다운 충돌 방지를 위해 순수 텍스트로 안전하게 전송
clean_report = ai_report.replace("**", "")
final_message = f"📈 [오늘의 VIP 주식 브리핑]\n\n{clean_report}"

telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
payload = {
    "chat_id": TELEGRAM_CHAT_ID,
    "text": final_message
}

res = requests.post(telegram_url, data=payload)

if res.status_code == 200:
    print("\n🎉 성공! 텔레그램으로 브리핑이 전송되었습니다.")
else:
    print(f"\n❌ 텔레그램 전송 실패 (상태 코드 {res.status_code}): {res.text}")