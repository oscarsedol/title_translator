import streamlit as st
import google.generativeai as genai
import os
import time
from dotenv import load_dotenv

# --- 환경변수 및 API 설정 ---
load_dotenv()

# 🔒 [보안 기능] Secrets에서 아이디/비밀번호 가져오기
VALID_USERNAME = st.secrets.get("APP_USERNAME", os.getenv("APP_USERNAME", "owner"))
VALID_PASSWORD = st.secrets.get("APP_PASSWORD", os.getenv("APP_PASSWORD", "password123"))

# --- 로그인 UI 처리 ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.set_page_config(page_title="🔒 로그인", page_icon="🔐", layout="centered")
    st.title("🔐 시스템 접근 제한")
    st.subheader("이 앱은 허가된 사용자만 사용할 수 있습니다.")
    st.write("このアプリは許可されたユーザーのみ使用できます。")
    
    with st.form("login_form", clear_on_submit=False):
        login_user = st.text_input("Username / ID", key="login_user")
        login_pass = st.text_input("Password / パスワード", type="password", key="login_pass")
        submit_login = st.form_submit_button("🔑 로그인 / ログイン", type="primary", use_container_width=True)
        
        if submit_login:
            if login_user == VALID_USERNAME and login_pass == VALID_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("아이디 또는 비밀번호가 틀렸습니다. / IDまたはパスワードが間違っています。")
    st.stop()

# --- 로그인 성공 시 아래 본 프로그램 실행 ---
api_key = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
else:
    st.error("앗, .env 파일이나 Secrets에 GEMINI_API_KEY가 없어. 확인해줘, 주인.")

# --- 번역 가능 언어 목록 (가나다순 30개 언어) ---
LANGUAGES = {
    "네덜란드어 / オランダ語": "Dutch",
    "노르웨이어 / ノルウェー語": "Norwegian",
    "덴마크어 / デンマーク語": "Danish",
    "독일어 / ドイツ語": "German",
    "러시아어 / ロシア語": "Russian",
    "말레이어 / マレー語": "Malay",
    "베트남어 / ベトナム語": "Vietnamese",
    "스웨덴어 / スウェーデン語": "Swedish",
    "스페인어 / スペイン語": "Spanish",
    "아랍어 / アラビア語": "Arabic",
    "영어 / 英語": "English",
    "우즈베크어 / ウズベク語": "Uzbek",
    "우크라이나어 / ウクライナ語": "Ukrainian",
    "이탈리아어 / イタリア語": "Italian",
    "인도네시아어 / インドネシア語": "Indonesian",
    "일본어 / 日本語": "Japanese",
    "중국어(간체) / 中国語(簡体字)": "Simplified Chinese",
    "중국어(대만) / 中国語(台湾)": "Traditional Chinese (Taiwan)",
    "중국어(홍콩) / 中国語(香港)": "Traditional Chinese (Hong Kong)",
    "카자흐어 / カザフ語": "Kazakh",
    "태국어 / タイ語": "Thai",
    "튀르키예어 / トルコ語": "Turkish",
    "페르시아어 / ペルシア語": "Persian",
    "포르투갈어 / ポルトガル語": "Portuguese",
    "폴란드어 / ポーランド語": "Polish",
    "프랑스어 / フランス語": "French",
    "핀란드어 / フィンランド語": "Finnish",
    "필리핀어 / フィリピン語": "Filipino",
    "한국어 / 韓国語": "Korean",
    "힌디어 / ヒンディー語": "Hindi"
}

# --- 스트림릿 세션 상태 초기화 ---
for lang in LANGUAGES.keys():
    key = f"chk_{lang}"
    if key not in st.session_state:
        st.session_state[key] = ("한국어" in lang)

if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False
if 'results' not in st.session_state:
    st.session_state.results = {}

# --- 콜백 함수 ---
def select_all():
    for lang in LANGUAGES.keys():
        st.session_state[f"chk_{lang}"] = True

def deselect_all():
    for lang in LANGUAGES.keys():
        st.session_state[f"chk_{lang}"] = False

# --- 번역 및 100자 무결성 검증 함수 ---
def translate_and_verify_metadata(orig_title, orig_desc, target_lang, selected_model, progress_bar, status_text):
    model = genai.GenerativeModel(selected_model)
    
    # "사용한 음원 라이선스 코드" 문구 번역 규칙 추가
    prompt_base = f"""
    You are an expert YouTube SEO translator. Translate the following YouTube Title and Description to {target_lang}.
    CRITICAL RULES:
    1. Maintain the overall structure, tone, and formatting of the original.
    2. Keep ALL brackets, emojis, and special symbols (e.g., (), [], !, ?) exactly as they are used.
    3. The translated Title MUST be strictly under 100 characters (including spaces).
    4. ABSOLUTELY DO NOT output the original text. You MUST translate the content entirely into {target_lang}. Copying the original language is strictly forbidden.
    5. Carefully preserve the original tone, nuance, style, and vibe of the speech (e.g., formal/informal politeness, slang, emotional expressions). Make it sound natural while respecting the original context.
    6. Translate the phrase "사용한 음원 라이선스 코드" (which means 'Used Audio License Code') into {target_lang}.
    7. Output strictly in the following format without markdown blocks:
    [TITLE_START]
    (Translated Title in {target_lang})
    [TITLE_END]
    [DESC_START]
    (Translated Description in {target_lang})
    [DESC_END]
    [LABEL_START]
    (Translated phrase for "사용한 음원 라이선스 코드" in {target_lang})
    [LABEL_END]
    
    Original Title:
    {orig_title}
    
    Original Description:
    {orig_desc}
    """
    
    attempt = 1
    while attempt <= 3:
        if not st.session_state.is_processing:
            return None, None, None
            
        status_text.text(f"[{target_lang}] 번역 및 100자 검증 중... ({attempt}/3)")
        progress_bar.progress(int(attempt * (100 / 3)))
        
        try:
            response = model.generate_content(prompt_base)
            text = response.text.strip()
            
            # 텍스트 파싱
            title_part = ""
            desc_part = ""
            label_part = ""
            
            if "[TITLE_START]" in text and "[TITLE_END]" in text:
                title_part = text.split("[TITLE_START]")[1].split("[TITLE_END]")[0].strip()
            if "[DESC_START]" in text and "[DESC_END]" in text:
                desc_part = text.split("[DESC_START]")[1].split("[DESC_END]")[0].strip()
            if "[LABEL_START]" in text and "[LABEL_END]" in text:
                label_part = text.split("[LABEL_START]")[1].split("[LABEL_END]")[0].strip()
                
            # 100자 제한 검증
            if len(title_part) > 100:
                status_text.text(f"[{target_lang}] 제목이 100자를 초과했습니다({len(title_part)}자). 재시도 중...")
                prompt_base += f"\n\nCorrection Request: The translated title '{title_part}' is {len(title_part)} characters. It MUST be under 100 characters. Please shorten the title while keeping the meaning."
                time.sleep(2)
                attempt += 1
                continue
                
            if not title_part or not desc_part:
                prompt_base += f"\n\nCorrection Request: Output format was incorrect. Please strictly follow the [TITLE_START] and [DESC_START] format."
                time.sleep(2)
                attempt += 1
                continue
            
            status_text.text(f"[{target_lang}] 완료! ({attempt}회 만에 성공)")
            progress_bar.progress(100)
            return title_part, desc_part, label_part

        except Exception as e:
            status_text.text(f"[{target_lang}] 에러 발생: {e}")
            time.sleep(3)
            attempt += 1
            
    status_text.text(f"[{target_lang}] 3회 시도 실패. 건너뜁니다.")
    progress_bar.progress(100)
    return None, None, None

# --- UI 레이아웃 구성 ---
st.set_page_config(page_title="유튜브 제목/설명 번역기", page_icon="📝", layout="wide")

st.title("유튜브 제목 & 설명 글로벌 번역기 📝")
st.markdown("---")

is_locked = st.session_state.is_processing

# 1. 제목 / 설명 입력란 (글자 수 제한 적용)
col1, col2 = st.columns([1, 1])
with col1:
    st.subheader("원본 제목 (최대 100자)")
    orig_title = st.text_input("유튜브 제목을 입력하세요.", max_chars=100, disabled=is_locked)
    
with col2:
    st.subheader("원본 설명 (최대 5000자)")
    orig_desc = st.text_area("유튜브 설명을 입력하세요.", max_chars=5000, height=200, disabled=is_locked)

# 3. 음원 라이선스 코드 입력란
st.markdown("---")
st.subheader("🎵 음원 라이선스 코드 (선택)")
orig_license = st.text_area("번역된 설명란 맨 하단에 '사용한 음원 라이선스 코드' 안내 문구와 함께 덧붙일 코드를 입력해줘.", height=100, disabled=is_locked)

# 4. 제미나이 모델 선택 라디오 버튼
st.markdown("---")
MODEL_OPTIONS = {
    "Gemini 3.5 Flash (한국어 번역시 추천)": "gemini-3.5-flash",
    "Gemini 3.1 Flash-Lite (한국어 외 다국어 번역시 추천)": "gemini-3.1-flash-lite"
}
selected_model_label = st.radio(
    "사용할 제미나이 모델을 선택해줘, 주인.",
    options=list(MODEL_OPTIONS.keys()),
    index=0,  # 기본 선택은 3.5 플래시
    disabled=is_locked
)
selected_model = MODEL_OPTIONS[selected_model_label]

st.markdown("---")
st.subheader("🌐 번역할 언어 선택")
btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 6])
with btn_col1:
    st.button("전체 선택", on_click=select_all, use_container_width=True, disabled=is_locked)
with btn_col2:
    st.button("전체 해제", on_click=deselect_all, use_container_width=True, disabled=is_locked)

# 언어 개수가 많아졌으므로 4열 그리드로 배치
cols = st.columns(4) 
for i, lang in enumerate(LANGUAGES.keys()):
    with cols[i % 4]:
        st.checkbox(lang, key=f"chk_{lang}", disabled=is_locked)

st.markdown("---")
selected_langs = [lang for lang in LANGUAGES.keys() if st.session_state[f"chk_{lang}"]]

# 2. 작업 시작 / 중단 버튼
if not st.session_state.is_processing:
    if st.button("✨ 번역 시작", type="primary", use_container_width=True):
        if not orig_title.strip() or not orig_desc.strip():
            st.warning("제목과 설명을 모두 입력해 줘, 주인.")
        elif not selected_langs:
            st.warning("번역할 언어를 하나 이상 선택해 줘.")
        else:
            st.session_state.is_processing = True
            st.session_state.results = {}
            st.rerun()
else:
    if st.button("🛑 작업 중단", type="primary", use_container_width=True):
        st.session_state.is_processing = False
        st.warning("작업을 중단했어. 화면을 갱신합니다.")
        time.sleep(1)
        st.rerun()

# --- 번역 처리 루프 ---
if st.session_state.is_processing and orig_title.strip() and orig_desc.strip():
    total_langs = len(selected_langs)
    st.subheader("📊 실시간 진행 상황")
    
    total_progress_bar = st.progress(0)
    total_status_text = st.empty()
    lang_progress_bar = st.progress(0)
    lang_status_text = st.empty()
    
    for idx, lang in enumerate(selected_langs):
        if not st.session_state.is_processing:
            break
            
        clean_lang_name = lang.split(" / ")[0] 
        total_status_text.text(f"전체 진행 상황: {idx+1} / {total_langs} 언어 작업 중 ({clean_lang_name})")
        target_lang_en = LANGUAGES[lang]
        
        # 모델 변수 및 라벨 반환값(t_label) 추가 
        t_title, t_desc, t_label = translate_and_verify_metadata(
            orig_title, 
            orig_desc, 
            target_lang_en,
            selected_model,
            lang_progress_bar, 
            lang_status_text
        )
        
        if t_title and t_desc:
            # 3. 원본 라이선스가 있다면 번역된 설명 뒤에 띄어쓰기와 함께 병합
            final_desc = t_desc
            if orig_license.strip():
                # 인공지능이 라벨 번역을 놓쳤을 경우의 기본값 방어 코드
                translated_label = t_label if t_label else "사용한 음원 라이선스 코드"
                final_desc += f"\n\n{translated_label}\n{orig_license.strip()}"
                
            st.session_state.results[lang] = {"title": t_title, "desc": final_desc}
            
        total_progress_bar.progress((idx + 1) / total_langs)

    st.session_state.is_processing = False
    st.rerun()

# --- 번역 결과 출력 및 복사 영역 ---
if st.session_state.results and not st.session_state.is_processing:
    st.markdown("---")
    st.subheader("🎉 번역 완료! (결과 확인 및 복사)")
    st.info("각 텍스트 블록 우측 상단에 있는 **'복사 아이콘'**을 누르면 클립보드에 바로 복사됩니다.")
    
    for lang, data in st.session_state.results.items():
        with st.expander(f"📌 {lang} 번역 결과", expanded=True):
            st.markdown(f"**제목** (글자 수: {len(data['title'])}/100자)")
            st.code(data['title'], language="text")
            
            st.markdown("**설명**")
            st.code(data['desc'], language="text")
