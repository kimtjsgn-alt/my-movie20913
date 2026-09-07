import datetime
import requests
import pandas as pd
import streamlit as st
from pytz import timezone

# -----------------------------------------------------------------------------
# 1. 페이지 기본 설정 및 스타일 정의
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="어제자 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 어제자 박스오피스 TOP 10")

# -----------------------------------------------------------------------------
# 2. 한국 시간(KST) 기준 '어제' 날짜 계산 함수
# -----------------------------------------------------------------------------
def get_yesterday_kst_string() -> str:
    """
    서버 시계 설정과 상관없이 한국 시간(Asia/Seoul) 기준으로 
    '어제' 날짜를 계산하여 'YYYYMMDD' 문자열로 반환합니다.
    """
    kst = timezone('Asia/Seoul')
    now_kst = datetime.datetime.now(kst)
    yesterday_kst = now_kst - datetime.timedelta(days=1)
    return yesterday_kst.strftime('%Y%m%d')

# -----------------------------------------------------------------------------
# 3. KOBIS API 데이터 호출 및 캐싱 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)  # 동일한 날짜 요청은 1시간(3600초) 동안 캐시를 사용함
def fetch_daily_box_office(target_date: str, api_key: str):
    """
    KOBIS API를 호출하여 데이터를 가져오고 예외 처리를 진행합니다.
    """
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": api_key,
        "targetDt": target_date
    }
    
    # API 요청 보내기 (타임아웃 10초 설정)
    response = requests.get(url, params=params, timeout=10)
    
    # HTTP 상태 코드가 200이 아닌 경우 에러 처리
    if response.status_code != 200:
        raise Exception(f"API 서버 응답 에러 (HTTP 상태 코드: {response.status_code})")
        
    data = response.json()
    
    # KOBIS 특이사항: 인증키 오류 등의 경우 status_code가 200으로 오면서 'faultInfo' 응답이 담김
    if "faultInfo" in data:
        message = data["faultInfo"].get("message", "알 수 없는 오류가 발생했습니다.")
        raise Exception(f"KOBIS 오류 발생: {message}")
        
    # 데이터 구조 검증
    box_office_result = data.get("boxOfficeResult", {})
    daily_list = box_office_result.get("dailyBoxOfficeList", [])
    
    if not daily_list:
        raise Exception("해당 날짜의 영화 목록 데이터가 비어 있습니다.")
        
    return daily_list

# -----------------------------------------------------------------------------
# 4. 메인 실행 로직
# -----------------------------------------------------------------------------

# Streamlit Secrets(비밀 금고)에서 API 키 불러오기
try:
    API_KEY = st.secrets["KOBIS_KEY"]
except Exception:
    st.error("🔑 API 키를 찾을 수 없습니다. `.streamlit/secrets.toml` 파일이나 Streamlit Cloud의 Secrets 설정에 `KOBIS_KEY`를 등록해 주세요.")
    st.stop()

# 한국 시간 기준 어제 날짜 구하기
target_date = get_yesterday_kst_string()
formatted_date = f"{target_date[:4]}년 {target_date[4:6]}월 {target_date[6:]}일"

st.caption(f"기준일자: {formatted_date} (한국 시간 기준)")

# API 호출 및 데이터 가공
try:
    raw_data = fetch_daily_box_office(target_date, API_KEY)
    
    # 파이썬 데이터프레임(DataFrame)으로 변환
    df = pd.DataFrame(raw_data)
    
    # 필요한 컬럼 정제 및 문자열 -> 숫자형 데이터 변환 (정렬 및 그래프용)
    df["rank"] = pd.to_numeric(df["rank"])
    df["rankInten"] = pd.to_numeric(df["rankInten"])
    df["audiCnt"] = pd.to_numeric(df["audiCnt"])
    df["audiAcc"] = pd.to_numeric(df["audiAcc"])
    df["scrnCnt"] = pd.to_numeric(df["scrnCnt"])

    # -------------------------------------------------------------------------
    # 1위 영화 지표 카드 (Metric) 출력
    # -------------------------------------------------------------------------
    top_movie = df.iloc[0]
    
    # 전일 대비 순위 변동 텍스트 가공
    rank_inten = top_movie["rankInten"]
    if rank_inten > 0:
        rank_delta = f"▲ {rank_inten}"
    elif rank_inten < 0:
        rank_delta = f"▼ {abs(rank_inten)}"
    else:
        rank_delta = "변동 없음"

    st.subheader(f"🥇 1위 영화 : {top_movie['movieNm']}")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("일일 관객수", f"{top_movie['audiCnt']:,} 명", delta=rank_delta)
    col2.metric("누적 관객수", f"{top_movie['audiAcc']:,} 명")
    col3.metric("스크린 수", f"{top_movie['scrnCnt']:,} 개")
    
    st.markdown("---")

    # -------------------------------------------------------------------------
    # 일일 관객수 상위 5편 막대그래프
    # -------------------------------------------------------------------------
    st.subheader("📊 관객수 상위 5편")
    top5_df = df.head(5).copy()
    
    # Streamlit 차트에 쓰기 위해 영화명을 인덱스로 지정하고 관객수 컬럼만 선택
    chart_data = top5_df.set_index("movieNm")[["audiCnt"]]
    chart_data.columns = ["일일 관객수"]
    
    st.bar_chart(chart_data)

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 박스오피스 전체 표 시각화
    # -------------------------------------------------------------------------
    st.subheader("📋 순위 목록")
    
    # 표에 보여줄 컬럼 선택 및 이름 변경
    display_df = df[[
        "rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"
    ]].copy()
    
    display_df.columns = [
        "순위", "영화명", "개봉일", "일일 관객수", "누적 관객수", "스크린 수"
    ]

    # Streamlit 데이터 프레임 출력 (숫자 세 자릿수 콤마 서식 적용)
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "일일 관객수": st.column_config.NumberColumn(format="%d 명"),
            "누적 관객수": st.column_config.NumberColumn(format="%d 명"),
            "스크린 수": st.column_config.NumberColumn(format="%d 개"),
        }
    )

except Exception as e:
    # 에러 발생 시 사용자 친화적인 안내 메시지 표시
    st.error(f"❌ 데이터를 불러오는 도중 오류가 발생했습니다: {e}")
    st.info(
        """
        **💡 아래 항목을 확인해 주세요:**
        1. **인증키 확인**: Streamlit Cloud Secrets 설정에 `KOBIS_KEY`가 올바르게 입력되었는지 확인해 주세요.
        2. **일일 요청 한도**: KOBIS API의 일일 호출 한도(3,000회)를 초과했는지 확인해 주세요.
        3. **집계 시간**: 새벽 시간에는 KOBIS 측의 전일자 집계가 아직 완료되지 않았을 수 있습니다.
        """
    )
