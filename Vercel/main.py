# -*- coding: utf-8 -*-
from flask import Flask, render_template, jsonify, request
import requests
import os
import re
import json
from collections import Counter
from konlpy.tag import Okt
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
import time

app = Flask(__name__)

# --- 전역 변수 대신, 구글 시트를 캐시처럼 활용 ---
# Vercel의 서버리스 환경은 전역 변수를 공유하지 않으므로,
# 구글 시트를 직접 읽어와 최신 상태를 유지합니다.

# --- 구글 시트 연동 설정 ---
try:
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    if 'GOOGLE_CREDENTIALS_JSON' in os.environ:
        creds_json = json.loads(os.environ['GOOGLE_CREDENTIALS_JSON'])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)

    client = gspread.authorize(creds)
    log_sheet = client.open("실시간 검색어 순위 데이터").worksheet('log')
    score_sheet = client.open("실시간 검색어 순위 데이터").worksheet('기사_점수')
    cache_sheet = client.open("실시간 검색어 순위 데이터").worksheet('캐시') # 최종 결과를 저장할 새 시트
    print("Google Sheets에 성공적으로 연결되었습니다.")
except Exception as e:
    print(f"--- Google Sheets 연결 상세 오류 ---\n{e}\n---------------------------------")
    log_sheet, score_sheet, cache_sheet = None, None, None
# -----------------------------

okt = Okt()

# (이전 코드의 함수들은 대부분 그대로 유지됩니다)
def get_article_pubdate(url):
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        date_tag = soup.select_one('span._ARTICLE_DATE_TIME[data-date-time], span.media_end_head_info_datestamp_time[data-date-time]')
        if date_tag:
            return datetime.strptime(date_tag['data-date-time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo("Asia/Seoul"))
    except Exception: pass
    return None

def get_recency_score(pub_date):
    if not pub_date: return 0.8
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    age = now_kst - pub_date
    if age < timedelta(hours=1): return 1.2
    if age < timedelta(hours=3): return 1.0
    return 0.8

def get_off_peak_bonus():
    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    if now_kst.weekday() >= 5 or 0 <= now_kst.hour <= 6: return 1.1
    return 1.0

def crawl_and_analyze():
    target_url = "https://news.naver.com/main/ranking/popularDay.naver"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(target_url, headers=headers)
        soup = BeautifulSoup(response.text, 'lxml')
        selectors = ['.rankingnews_box ul.rankingnews_list > li', '.rankingnews_list li']
        all_articles_li = []
        for selector in selectors:
            all_articles_li = soup.select(selector)
            if all_articles_li: break
        if not all_articles_li: return {}, {}, {}

        all_keywords_details = []
        ranked_articles_for_sheet = []
        off_peak_bonus = get_off_peak_bonus()

        for rank, item in enumerate(all_articles_li, 1):
            try:
                title_tag = item.select_one('.list_title, .list_text a, a')
                if not title_tag: continue
                title = title_tag.get('title', '').strip() or title_tag.text.strip()
                link = title_tag.get('href')
                pub_date = get_article_pubdate(link)
                recency_score = get_recency_score(pub_date)
                breaking_news_bonus = 1.2 if '[속보]' in title else 1.0
                time.sleep(0.05)
                article_id_match = re.search(r'aid=(\d+)', link) or re.search(r'/(\d{10})', link.split('?')[0])
                if not article_id_match: continue
                article_id = article_id_match.group(1)
                base_score = max(0, 101 - rank) 
                total_score = base_score * breaking_news_bonus * recency_score * off_peak_bonus
                pub_date_str = pub_date.strftime('%Y-%m-%d %H:%M:%S') if pub_date else "N/A"
                ranked_articles_for_sheet.append([article_id, title, link, rank, pub_date_str, round(total_score, 2)])
                pos_tagged = okt.pos(title, norm=True, stem=True)
                stopwords = set(['속보', '뉴스', '종합', '기자', '사진', '영상', '단독', '포토', '오늘'])
                meaningful_pos = [p for p in pos_tagged if len(p[0]) > 1 and p[0] not in stopwords and p[1] in ['Noun', 'ProperNoun', 'Alpha']]
                for n in range(1, 4):
                    if n > len(meaningful_pos): continue
                    for i in range(len(meaningful_pos) - n + 1):
                        ngram_tuples = meaningful_pos[i : i + n]
                        if n == 1 and ngram_tuples[0][1] != 'ProperNoun': continue
                        ngram_phrase = " ".join([t[0] for t in ngram_tuples])
                        all_keywords_details.append({'keyword': ngram_phrase, 'score': total_score, 'link': link})
            except Exception: continue
        
        all_keywords_details.sort(key=lambda x: x['score'], reverse=True)
        current_frequencies = Counter(item['keyword'] for item in all_keywords_details)
        keyword_to_all_links = {kw: set() for kw in current_frequencies}
        for item in all_keywords_details: keyword_to_all_links[item['keyword']].add(item['link'])
        keyword_best_links = {item['keyword']: item['link'] for item in reversed(all_keywords_details)}
        
        if score_sheet and ranked_articles_for_sheet:
            ranked_articles_for_sheet.sort(key=lambda x: x[5], reverse=True)
            score_sheet.clear()
            score_sheet.update('A1', [['기사_ID', '제목', '링크', '랭킹_페이지_순위', '발행_시간', '최종_점수']])
            score_sheet.update('A2', ranked_articles_for_sheet)
        return current_frequencies, keyword_to_all_links, keyword_best_links
    except Exception as e:
        print(f"크롤링 및 분석 중 오류 발생: {e}")
        return {}, {}, {}

def get_historical_averages():
    if not log_sheet: return {}
    try:
        all_data = pd.DataFrame(log_sheet.get_all_records())
        if all_data.empty: return {}
        all_data['Timestamp'] = pd.to_datetime(all_data['Timestamp'])
        now = datetime.now()
        past_start, past_end = now - timedelta(minutes=30), now - timedelta(minutes=5)
        historical_data = all_data[(all_data['Timestamp'] >= past_start) & (all_data['Timestamp'] < past_end)]
        return historical_data.groupby('Keyword')['Frequency'].mean().to_dict() if not historical_data.empty else {}
    except Exception: return {}

def log_to_sheet(frequencies):
    if not log_sheet: return
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    rows_to_add = [[timestamp, keyword, count] for keyword, count in frequencies.items()]
    if rows_to_add:
        try:
            log_sheet.append_rows(rows_to_add, value_input_option='USER_ENTERED')
        except Exception: pass

# --- Vercel Cron Job이 호출할 API 엔드포인트 ---
@app.route('/api/cron', methods=['GET'])
def cron_job():
    # Vercel 환경 변수에 저장된 CRON_SECRET과 비교하여 보안 강화
    auth_header = request.headers.get('Authorization')
    cron_secret = os.environ.get('CRON_SECRET')
    if not cron_secret or auth_header != f"Bearer {cron_secret}":
        return jsonify({"status": "unauthorized"}), 401
    
    print(f"[{datetime.now()}] Cron Job으로 순위 업데이트 작업을 시작합니다.")
    
    # 이전 순위 가져오기 (이제는 캐시 시트에서)
    previous_ranks = {}
    if cache_sheet:
        try:
            previous_data = cache_sheet.get_all_records()
            previous_ranks = {item['keyword']: i + 1 for i, item in enumerate(previous_data)}
        except Exception: pass

    current_frequencies, keyword_to_all_links, keyword_best_links = crawl_and_analyze()
    if not current_frequencies:
        return jsonify({"status": "no keywords to analyze"}), 500

    historical_averages = get_historical_averages()
    rise_rates = {}
    for keyword, current_freq in current_frequencies.items():
        historical_avg = historical_averages.get(keyword, 0)
        rate = (current_freq * 10) / (historical_avg + 1)
        num_words = keyword.count(' ') + 1
        if num_words > 1: rate *= num_words
        rise_rates[keyword] = rate

    sorted_keywords = sorted(rise_rates.items(), key=lambda item: item[1], reverse=True)
    
    filtered_keywords = []
    JACCARD_THRESHOLD = 0.5 
    for keyword, rate in sorted_keywords:
        is_similar = False
        current_links = keyword_to_all_links.get(keyword, set())
        for representative_kw, _ in filtered_keywords:
            representative_links = keyword_to_all_links.get(representative_kw, set())
            intersection = len(current_links.intersection(representative_links))
            union = len(current_links.union(representative_links))
            if union > 0 and (intersection / union) > JACCARD_THRESHOLD:
                is_similar = True
                break
        if not is_similar:
            filtered_keywords.append((keyword, rate))

    final_results = []
    for new_rank, (keyword, rate) in enumerate(filtered_keywords[:50], 1):
        old_rank = previous_ranks.get(keyword)
        change = "new"
        if old_rank is not None:
            if old_rank > new_rank: change = f"up_{old_rank - new_rank}"
            elif old_rank < new_rank: change = f"down_{new_rank - old_rank}"
            else: change = "same_0"
        final_results.append({'keyword': keyword, 'link': keyword_best_links.get(keyword, '#'), 'rank_change': change})

    # 최종 결과를 '캐시' 시트에 저장
    if cache_sheet and final_results:
        now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
        am_pm = "오후" if now_kst.hour >= 12 else "오전"
        hour_12 = now_kst.hour % 12 or 12
        last_updated_str = f"{now_kst.month}월 {now_kst.day}일, {am_pm} {hour_12}:{now_kst.strftime('%M')} 업데이트됨"
        
        cache_sheet.clear()
        # 헤더와 마지막 업데이트 시간, 그리고 순위 데이터를 한 번에 저장
        headers = [['keyword', 'link', 'rank_change', 'last_updated']]
        first_row = final_results[0]
        rows_to_write = [
            [first_row['keyword'], first_row['link'], first_row['rank_change'], last_updated_str]
        ]
        for item in final_results[1:]:
             rows_to_write.append([item['keyword'], item['link'], item['rank_change'], ''])
        
        cache_sheet.update('A1', headers)
        cache_sheet.update('A2', rows_to_write)

    log_to_sheet(current_frequencies)
    return jsonify({"status": "success", "updated_keywords": len(final_results)}), 200

# --- 사용자가 접속하는 경로 ---
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    """사용자에게 웹페이지를 보여주고, 캐시된 데이터를 전달합니다."""
    context = {'top_10': [], 'rest_of_keywords': [], 'last_updated': '업데이트 정보 로딩 중...'}
    if cache_sheet:
        try:
            data = cache_sheet.get_all_records()
            if data:
                context['last_updated'] = data[0]['last_updated']
                rankings = [{'keyword': r['keyword'], 'link': r['link'], 'rank_change': r['rank_change']} for r in data]
                context['top_10'] = rankings[:10]
                context['rest_of_keywords'] = rankings[10:]
        except Exception: pass
    return render_template('index.html', **context)

@app.route('/api/trends')
def api_trends():
    """프론트엔드에 최신 순위 데이터를 JSON 형태로 제공합니다."""
    data_to_send = {'rankings': [], 'last_updated': '업데이트 정보 로딩 중...'}
    if cache_sheet:
        try:
            data = cache_sheet.get_all_records()
            if data:
                data_to_send['last_updated'] = data[0]['last_updated']
                data_to_send['rankings'] = [{'keyword': r['keyword'], 'link': r['link'], 'rank_change': r['rank_change']} for r in data]
        except Exception: pass
    return jsonify(data_to_send)