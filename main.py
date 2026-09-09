import datetime
import requests
import pandas as pd
import streamlit as st
import altair as alt
from pytz import timezone

# -----------------------------------------------------------------------------
# 1. Streamlit 페이지 기본 설정
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="어제자 일별 박스오피스",
    page_icon="🎬",
    layout="wide"
)

st.title("🎬 어제자 박스오피스 TOP 10")

# -----------------------------------------------------------------------------
# 2. 한국 시간(KST) 기준 '어제' 날짜 계산 함수
# -----------------------------------------------------------------------------
def get_yesterday_kst_string() -> str:
    """
    배포 서버의 시계 설정과 상관없이 한국 시간(Asia/Seoul)을 기준으로
    '어제' 날짜를 구해 'YYYYMMDD' 형태의 8자리 문자열로 반환합니다.
    """
    kst = timezone('Asia/Seoul')
    now_kst = datetime.datetime.now(kst)
    yesterday_kst = now_kst - datetime.timedelta(days=1)
    return yesterday_kst.strftime('%Y%m%d')

# -----------------------------------------------------------------------------
# 3. KOBIS API 데이터 호출 및 1시간 기억(캐싱) 함수
# -----------------------------------------------------------------------------
@st.cache_data(ttl=3600)  # 동일한 날짜 요청은 1시간(3600초) 동안 캐시된 결과를 재사용
def fetch_daily_box_office(target_date: str, api_key: str):
    """
    KOBIS API를 호출하여 데이터를 가져오고 예외 상황을 처리합니다.
    """
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    params = {
        "key": api_key,
        "targetDt": target_date
    }
    
    # API 요청 보내기 (10초 타임아웃)
    response = requests.get(url, params=params, timeout=10)
    
    # 1. HTTP 네트워크 요청 실패 처리
    if response.status_code != 200:
        raise Exception(f"API 서버 네트워크 응답 에러 (HTTP 상태 코드: {response.status_code})")
        
    data = response.json()
    
    # 2. KOBIS 오류 상자(faultInfo) 체크
    if "faultInfo" in data:
        message = data["faultInfo"].get("message", "알 수 없는 오류가 발생했습니다.")
        raise Exception(f"KOBIS 오류 발생: {message}")
        
    # 3. 영화 목록 데이터 존재 여부 검증
    box_office_result = data.get("boxOfficeResult", {})
    daily_list = box_office_result.get("dailyBoxOfficeList", [])
    
    if not daily_list:
        raise Exception("해당 날짜의 영화 목록 데이터가 비어 있습니다.")
        
    return daily_list

# -----------------------------------------------------------------------------
# 4. 메인 프로그램 실행 로직
# -----------------------------------------------------------------------------

# Streamlit 비밀 금고(secrets)에서 KOBIS_KEY 인증키 불러오기
try:
    API_KEY = st.secrets["KOBIS_KEY"]
except Exception:
    st.error("🔑 API 키를 찾을 수 없습니다.")
    st.info(
        """
        **확인 사항:**
        - 로컬 환경: 프로젝트 폴더 안 `.streamlit/secrets.toml` 파일에 `KOBIS_KEY = "발급받은키"`가 추가되어 있는지 확인하세요.
        - Streamlit Cloud: 앱 설정의 **Secrets** 메뉴에 `KOBIS_KEY`를 설정했는지 확인하세요.
        """
    )
    st.stop()

# 한국 시간 기준 어제 날짜 구하기
target_date = get_yesterday_kst_string()
formatted_date = f"{target_date[:4]}년 {target_date[4:6]}월 {target_date[6:]}일"

st.caption(f"📅 기준일자: {formatted_date} (한국 시간 기준)")

# API 데이터 불러오기 및 시각화 처리
try:
    raw_data = fetch_daily_box_office(target_date, API_KEY)
    
    # 데이터프레임 변환
    df = pd.DataFrame(raw_data)
    
    # 숫자 문자열을 실제 숫자형 데이터로 변환
    df["rank"] = pd.to_numeric(df["rank"])
    df["rankInten"] = pd.to_numeric(df["rankInten"])
    df["audiCnt"] = pd.to_numeric(df["audiCnt"])
    df["audiAcc"] = pd.to_numeric(df["audiAcc"])
    df["scrnCnt"] = pd.to_numeric(df["scrnCnt"])

    # -------------------------------------------------------------------------
    # 가. 1위 영화 지표 카드 3개 출력
    # -------------------------------------------------------------------------
    top_movie = df.iloc[0]  # 1위 영화 데이터
    
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
    # 나. 관객수 상위 5편 막대그래프 (Altair를 이용해 오름차순 순서 완벽 고정)
    # -------------------------------------------------------------------------
    st.subheader("📊 관객수 상위 5편 (관객수 적은 순 ➡️ 많은 순)")
    
    # 1~5위 영화 추출 후 관객수 오름차순 정렬
    top5_asc_df = df.head(5).sort_values(by="audiCnt", ascending=True)
    
    # Altair 차트 작성 (sort='x' 옵션으로 관객수 오름차순 순서를 강제 지정)
    chart = alt.Chart(top5_asc_df).mark_bar().encode(
        x=alt.X('movieNm:N', sort=top5_asc_df['movieNm'].tolist(), title="영화명"),
        y=alt.Y('audiCnt:Q', title="일일 관객수"),
        tooltip=['movieNm', 'audiCnt']
    ).properties(
        height=350
    )
    
    st.altair_chart(chart, use_container_width=True)

    st.markdown("---")

    # -------------------------------------------------------------------------
    # 다. 전체 영화 목록 표(Table) 시각화 - 관객수 오름차순 정렬
    # -------------------------------------------------------------------------
    st.subheader("📋 전체 박스오피스 순위 (일일 관객수 오름차순 정렬)")
    
    # 전체 영화 목록도 관객수 오름차순으로 정렬
    df_sorted = df.sort_values(by="audiCnt", ascending=True)
    
    display_df = df_sorted[[
        "rank", "movieNm", "openDt", "audiCnt", "audiAcc", "scrnCnt"
    ]].copy()
    
    display_df.columns = [
        "순위", "영화명", "개봉일", "일일 관객수", "누적 관객수", "스크린 수"
    ]

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
    st.error(f"❌ 박스오피스 정보를 불러오는 데 실패했습니다: {e}")
    st.warning(
        """
        **💡 아래 사항을 확인해 주세요:**
        1. **인증키(KOBIS_KEY)가 정확한지 확인**: Streamlit Cloud Secrets에 입력한 키 값이 맞는지 확인해 주세요.
        2. **일일 호출 한도 초과 여부**: KOBIS API는 하루 최대 3,000회까지만 요청할 수 있습니다.
        3. **집계 마감 시간 안내**: 새벽 일찍 접속 시 영화진흥위원회의 전일 자 박스오피스 집계가 진행 중일 수 있습니다.
        """
    )
