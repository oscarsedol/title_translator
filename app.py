import streamlit as st
import google.generativeai as genai
import os
import pysrt
import time
import re
import zipfile
import io
from dotenv import load_dotenv

# --- 환경변수 및 API 설정 / 環境変数 및 API 設定 ---
load_dotenv()

# 🔒 [보안 기능] Secrets에서 아이디/비밀번호 가져오기
VALID_USERNAME = st.secrets.get("APP_USERNAME", os.getenv("APP_USERNAME", "owner"))
VALID_PASSWORD = st.secrets.get("APP_PASSWORD", os.getenv("APP_PASSWORD", "password123"))

# --- 로그인 UI 처리 / ログインUI処理 ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.set_page_config(page_title="🔒 로그인 / ログイン", page_icon="🔐", layout="centered")
    st.title("🔐 시스템 접근 제한 / アクセス制限")
    st.subheader("이 앱은 허가된 사용자만 사용할 수 있습니다.")
    st.write("このアプリは許可されたユーザーのみ使用できます。")
    
    login_user = st.text_input("Username / ID", key="login_user")
    login_pass = st.text_input("Password / パスワード", type="password", key="login_pass")
    
    if st.button("🔑 로그인 / ログイン", type="primary", use_container_width=True):
        if login_user == VALID_USERNAME and login_pass == VALID_PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("아이디 또는 비밀번호가 틀렸습니다. / IDまたはパスワードが間違っています。")
    st.stop()  # 로그인 성공 전까지는 아래 코드를 절대 실행하지 않고 멈춤

# --- 로그인 성공 시 아래의 본 프로그램 실행 ---

api_key = os.getenv("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
else:
    st.error("앗, .env 파일이나 Secrets에 GEMINI_API_KEY가 없어. 확인해줘, 주인.")

# 3.1 플래시 라이트로 고정하여 가성비 극대화!
MODEL_NAME = 'gemini-3.1-flash-lite'

# --- 번역 가능 언어 목록 (확장판) / 翻訳可能言語リスト ---
LANGUAGES = {
    "한국어 / 韓国語": "Korean", 
    "일본어 / 日本語": "Japanese", 
    "영어 / 英語": "English",
    "인도네시아어 / インドネシア語": "Indonesian", 
    "대만어(번체) / 台湾語(繁体字)": "Traditional Chinese (Taiwan)",
    "중국어(간체) / 中国語(簡体字)": "Simplified Chinese",
    "베트남어 / ベトナム語": "Vietnamese", 
    "태국어 / タイ語": "Thai", 
    "말레이시아어 / マレーシア語": "Malay",
    "러시아어 / ロシア語": "Russian", 
    "타갈로그어 / タガログ語": "Tagalog",
    "스페인어 / スペイン語": "Spanish", 
    "포르투갈어 / ポルトガル語": "Portuguese",
    "프랑스어 / フランス語": "French",
    "독일어 / ドイツ語": "German",
    "이탈리아어 / イタリア語": "Italian",
    "우즈베크어 / ウズベク語": "Uzbek",
    "카자흐어 / カザフ語": "Kazakh",
    "튀르키예어 / トルコ語": "Turkish",
    "힌디어 / ヒンディー語": "Hindi",
    "아랍어 / アラビア語": "Arabic",
    "스웨덴어 / スウェーデン語": "Swedish",
    "노르웨이어 / ノルウェー語": "Norwegian",
    "덴마크어 / デンマーク語": "Danish",
    "핀란드어 / フィンランド語": "Finnish"
}

# --- 스트림릿 세션 상태 초기화 / セッション状態の初期化 ---
for lang in LANGUAGES.keys():
    key = f"chk_{lang}"
    if key not in st.session_state:
        st.session_state[key] = ("일본어 / 日本語" not in lang)

if 'is_processing' not in st.session_state:
    st.session_state.is_processing = False
if 'results' not in st.session_state:
    st.session_state.results = {}
if 'video_title' not in st.session_state:
    st.session_state.video_title = ""

# --- 콜백 함수 / コールバック関数 ---
def select_all():
    for lang in LANGUAGES.keys():
        st.session_state[f"chk_{lang}"] = True

def deselect_all():
    for lang in LANGUAGES.keys():
        st.session_state[f"chk_{lang}"] = False

def verify_timeline_final(original_srt, translated_srt_text):
    try:
        translated_srt = pysrt.from_string(translated_srt_text)
        if len(original_srt) != len(translated_srt):
            return False, "세그먼트 개수 불일치 / セグメント数の不一致"
        for orig, trans in zip(original_srt, translated_srt):
            if orig.start != trans.start or orig.end != trans.end:
                return False, f"타임라인 불일치 / タイムラインの不一致 (Index {orig.index})"
        return True, "무결성 완벽함 / 整合性完璧"
    except Exception as e:
        return False, f"SRT 파싱 에러 / SRTパースエラー: {e}"

# --- 번역 및 타임라인 강제 동기화 / 翻訳およびタイムライン同期 ---
def translate_and_verify(original_text, original_srt, target_lang, progress_bar, status_text):
    model = genai.GenerativeModel(MODEL_NAME)
    
    prompt_base = f"""
    You are an expert subtitle translator. Translate the following SRT file to {target_lang}.
    CRITICAL RULES:
    1. Keep the exact same number of subtitle blocks. The original has {len(original_srt)} blocks.
    2. DO NOT merge, combine, or split lines. Translate line by line.
    3. Output ONLY the raw SRT format. NO markdown tags like ```srt. Just start with '1'.
    
    Original SRT:
    {original_text}
    """
    
    attempt = 1
    while attempt <= 3:
        if not st.session_state.is_processing:
            return None
            
        status_text.text(f"[{target_lang}] 번역 및 무결성 확보 중... / 翻訳および整合性確認中... ({attempt}/3)")
        progress_bar.progress(int(attempt * (100 / 3)))
        
        try:
            response = model.generate_content(prompt_base)
            translated_text = response.text.replace("```srt", "").replace("```", "").strip()
            
            try:
                translated_srt = pysrt.from_string(translated_text)
            except Exception:
                prompt_base += f"\n\nCorrection Request: Failed to parse your SRT output. Please ensure strict standard SRT syntax."
                time.sleep(2)
                attempt += 1
                continue

            if len(original_srt) != len(translated_srt):
                status_text.text(f"[{target_lang}] 문장 개수 불일치. 재시도 중... / 文章数の不一致。再試行中...")
                prompt_base += f"\n\nCorrection Request: Segment count mismatch! Try again."
                time.sleep(2)
                attempt += 1
                continue
            
            final_output = []
            for i in range(len(original_srt)):
                orig = original_srt[i]
                trans_text = translated_srt[i].text
                start_str = f"{orig.start.hours:02}:{orig.start.minutes:02}:{orig.start.seconds:02},{orig.start.milliseconds:03}"
                end_str = f"{orig.end.hours:02}:{orig.end.minutes:02}:{orig.end.seconds:02},{orig.end.milliseconds:03}"
                block = f"{orig.index}\n{start_str} --> {end_str}\n{trans_text}"
                final_output.append(block)
            
            status_text.text(f"[{target_lang}] 완료! / 完了! ({attempt}회 만에 성공 / {attempt}回目で成功)")
            progress_bar.progress(100)
            return "\n\n".join(final_output)

        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "Quota" in err_msg or "quota" in err_msg:
                match = re.search(r"retry in ([\d\.]+)\s*s", err_msg)
                wait_time = int(float(match.group(1))) + 2 if match else 25
                status_text.text(f"⚠️ [API 한도 / API制限] {wait_time}초 대기 후 재시도... / {wait_time}秒待機後、再試行...")
                time.sleep(wait_time)
                continue
            else:
                status_text.text(f"[{target_lang}] 에러 발생 / エラー発生: {e}")
                time.sleep(3)
                attempt += 1
            
    status_text.text(f"[{target_lang}] 3회 시도 실패. 건너뜁니다. / 3回の試行失敗。スキップします。")
    progress_bar.progress(100)
    return None

# --- UI 레이아웃 구성 / UIレイアウト構成 ---
st.set_page_config(page_title="SRT 다국어 번역기 / SRT多言語翻訳機", page_icon="🌐", layout="centered")

st.title("글로벌 자막 번역기 🚀")
st.subheader("グローバル字幕翻訳機")
st.markdown("---")

is_locked = st.session_state.is_processing

# 1. 파일 업로드란
uploaded_file = st.file_uploader("원본 SRT 파일을 올려줘, 주인. / 元のSRTファイルをアップロードしてください。", type=['srt'], disabled=is_locked)

# 2. 영상 제목 입력란
video_title = st.text_input("영상 제목을 입력해줘. (파일명에 사용됨) / 動画のタイトルを入力してください。(ファイル名に使用)", value=st.session_state.video_title, disabled=is_locked)
st.session_state.video_title = video_title

st.markdown("---")
st.subheader("🌐 번역할 언어 선택 / 翻訳する言語の選択")
btn_col1, btn_col2, btn_col3 = st.columns([1.5, 1.5, 3])
with btn_col1:
    st.button("전체 선택 / 全選択", on_click=select_all, use_container_width=True, disabled=is_locked)
with btn_col2:
    st.button("전체 해제 / 全解除", on_click=deselect_all, use_container_width=True, disabled=is_locked)

cols = st.columns(3) 
for i, lang in enumerate(LANGUAGES.keys()):
    with cols[i % 3]:
        st.checkbox(lang, key=f"chk_{lang}", disabled=is_locked)

st.markdown("---")
selected_langs = [lang for lang in LANGUAGES.keys() if st.session_state[f"chk_{lang}"]]

# 3. 작업 시작 / 중단 버튼
if not st.session_state.is_processing:
    if st.button("✨ 번역 시작 / 翻訳開始", type="primary", use_container_width=True):
        if not uploaded_file:
            st.warning("먼저 원본 SRT 파일을 업로드해 줘. / まず元のSRTファイルをアップロードしてください。")
        elif not video_title.strip():
            st.warning("영상 제목을 입력해 줘, 주인. / 動画のタイトルを入力してください。")
        elif not selected_langs:
            st.warning("번역할 언어를 하나 이상 선택해 줘. / 翻訳する言語を1つ以上選択してください。")
        else:
            st.session_state.is_processing = True
            st.session_state.results = {}
            st.rerun()
else:
    if st.button("🛑 작업 중단 / 作業中断", type="primary", use_container_width=True):
        st.session_state.is_processing = False
        st.warning("작업을 중단했어, 주인. 화면을 갱신합니다. / 作業を中断しました。画面を更新します。")
        time.sleep(1)
        st.rerun()

# --- 실제 번역 처리 루프 / 翻訳処理ループ ---
if st.session_state.is_processing and uploaded_file and video_title.strip():
    
    # 💡 3중 인코딩 방어막 적용 (UTF-8 -> CP949 -> Shift-JIS)
    raw_bytes = uploaded_file.getvalue()
    try:
        original_content = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            original_content = raw_bytes.decode("cp949")
        except UnicodeDecodeError:
            original_content = raw_bytes.decode("shift_jis")
            
    try:
        original_srt = pysrt.from_string(original_content)
    except Exception as e:
        st.error(f"SRT 파일을 파싱하는 중 오류가 발생했어 / SRTファイルのパース中にエラーが発生しました: {e}")
        st.session_state.is_processing = False
        st.stop()

    total_langs = len(selected_langs)
    st.subheader("📊 실시간 진행 상황 / リアルタイム進行状況")
    
    total_progress_bar = st.progress(0)
    total_status_text = st.empty()
    lang_progress_bar = st.progress(0)
    lang_status_text = st.empty()
    
    for idx, lang in enumerate(selected_langs):
        if not st.session_state.is_processing:
            break
            
        clean_lang_name = lang.split(" / ")[0] 
        total_status_text.text(f"📊 전체 진행 상황: {idx+1} / {total_langs} 언어 작업 중 ({clean_lang_name}) \n 全体進行状況: {idx+1} / {total_langs} 言語作業中")
        target_lang_en = LANGUAGES[lang]
        
        translated_srt = translate_and_verify(
            original_content, 
            original_srt, 
            target_lang_en, 
            lang_progress_bar, 
            lang_status_text
        )
        
        if translated_srt:
            is_valid, msg = verify_timeline_final(original_srt, translated_srt)
            if is_valid:
                st.session_state.results[clean_lang_name] = translated_srt
            
        total_progress_bar.progress((idx + 1) / total_langs)

    st.session_state.is_processing = False
    st.rerun()

# --- 최종 검수 및 다운로드 영역 / 最終確認およびダウンロード領域 ---
if st.session_state.results and not st.session_state.is_processing:
    st.markdown("---")
    st.subheader("🎉 작업 완료 및 다운로드 / 作業完了およびダウンロード")
    
    results = st.session_state.results
    title = st.session_state.video_title.strip()
    
    st.success(f"총 {len(results)}개 언어의 자막이 완벽하게 준비됐어! / 計{len(results)}言語の字幕が完璧に準備されました！")
    
    if len(results) == 1:
        lang_name = list(results.keys())[0]
        srt_content = list(results.values())[0]
        file_name = f"{title}_{lang_name}.srt"
        
        st.download_button(
            label=f"📥 {file_name} 다운로드 / ダウンロード",
            data=srt_content.encode("utf-8-sig"), 
            file_name=file_name,
            mime="text/plain",
            type="primary",
            use_container_width=True
        )
    else:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            for lang_name, srt_content in results.items():
                file_name = f"{title}_{lang_name}.srt"
                zip_file.writestr(file_name, srt_content.encode("utf-8-sig"))
        
        zip_buffer.seek(0)
        zip_filename = f"{title}_자막들.zip"
        
        st.download_button(
            label=f"📦 {zip_filename} 전체 다운로드 / 一括ダウンロード",
            data=zip_buffer,
            file_name=zip_filename,
            mime="application/zip",
            type="primary",
            use_container_width=True
        )

    st.balloons()