import numpy as np
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing.image import img_to_array
from tensorflow.keras.models import Model

# 모델 불러오기
base_model = MobileNetV2(weights="imagenet", include_top=False, pooling='avg')
model = Model(inputs=base_model.input, outputs=base_model.output)

def extract_feature(image_pil):
    image_pil = image_pil.resize((224, 224)).convert("RGB")
    image_array = img_to_array(image_pil)
    image_array = np.expand_dims(image_array, axis=0)
    image_array = preprocess_input(image_array)
    features = model.predict(image_array)
    return features.flatten()
