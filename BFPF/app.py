# app.py
from flask import Flask, render_template, request, jsonify
from model.extractor import extract_features
from scipy.spatial.distance import cosine
import os

app = Flask(__name__)
# CORS가 필요 없도록 같은 도메인에서 처리

# 메모리에 일회 저장
embeddings = {}
roles = ['child','father','mother','pgrandpa','pgrandma','mgrandpa','mgrandma']
labels = {
    'child':'아이','father':'아빠','mother':'엄마',
    'pgrandpa':'친할아버지','pgrandma':'친할머니',
    'mgrandpa':'외할아버지','mgrandma':'외할머니'
}

@app.route('/')
def index():
    return render_template('index.html', roles=roles, labels=labels)

@app.route('/upload', methods=['POST'])
def upload():
    role = request.form.get('role')
    file = request.files.get('image')
    if role not in roles or not file:
        return jsonify({'error':'invalid request'}),400
    img_bytes = file.read()
    try:
        vec = extract_features(img_bytes)
    except Exception:
        return jsonify({'error':'model error'}),500
    embeddings[role] = vec.tolist()
    return jsonify({'status':'ok','role':role})

@app.route('/compare', methods=['POST'])
def compare():
    child = embeddings.get('child')
    if not child:
        return jsonify({'error':'아이 사진이 필요합니다.'}),400
    results = []
    for role, vec in embeddings.items():
        if role=='child': continue
        score = (1 - cosine(child, vec)) * 100
        results.append({'role':role,'label':labels[role],'similarity':round(score,2)})
    results.sort(key=lambda x: x['similarity'], reverse=True)
    best = results[0] if results else None
    return jsonify({'best_match':best,'all':results})

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',3000)))
