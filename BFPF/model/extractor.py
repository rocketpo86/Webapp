# model/extractor.py
import io
from PIL import Image, ImageOps
import numpy as np
import tensorflow as tf

# MobileNetV2 특징 추출 레이어만 사용
model = tf.keras.applications.MobileNetV2(
    input_shape=(224,224,3),
    include_top=False,
    pooling='avg',
    weights=None
)

def extract_features(image_bytes: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(image_bytes)).convert('RGB')
    img = ImageOps.fit(img, (224,224), Image.ANTIALIAS)
    arr = np.array(img)
    arr = tf.keras.applications.mobilenet_v2.preprocess_input(arr)
    arr = np.expand_dims(arr, axis=0)
    feats = model(arr)
    return feats.numpy()[0]
