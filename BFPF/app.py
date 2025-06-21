from flask import Flask, request, jsonify, render_template
import os
import numpy as np
from PIL import Image
from extractor import extract_feature

app = Flask(__name__)
features = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    try:
        role = request.form.get('role')
        image = request.files.get('image')
        if not role or not image:
            return jsonify({'status': 'fail', 'error': 'No role or image'}), 400

        img = Image.open(image.stream)
        feature = extract_feature(img)
        features[role] = feature.tolist()
        return jsonify({'status': 'ok'})
    except Exception as e:
        return jsonify({'status': 'fail', 'error': str(e)}), 500

@app.route('/compare', methods=['POST'])
def compare():
    try:
        if 'child' not in features:
            return jsonify({'status': 'fail', 'error': 'No child uploaded'}), 400

        child = np.array(features['child'])
        result = []
        for role, vec in features.items():
            if role == 'child':
                continue
            other = np.array(vec)
            sim = cosine_similarity(child, other)
            result.append({
                'label': role,
                'similarity': round(sim * 100, 2)
            })

        best = max(result, key=lambda x: x['similarity']) if result else None

        return jsonify({
            'status': 'ok',
            'best_match': best,
            'all': sorted(result, key=lambda x: x['similarity'], reverse=True)
        })
    except Exception as e:
        return jsonify({'status': 'fail', 'error': str(e)}), 500

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

if __name__ == '__main__':
    app.run(debug=True, port=3000)
