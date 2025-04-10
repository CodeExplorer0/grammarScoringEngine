# -*- coding: utf-8 -*-
"""grammarScoringEngine.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1RrgEvEanZ_aqRbV9JNcIQO6Z6dxp-ToJ
"""

# ====================================
# 📦 1. Imports
# ====================================
import os
import numpy as np
import pandas as pd
import librosa
import torch
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error
from scipy.stats import pearsonr
from transformers import Wav2Vec2Processor, Wav2Vec2Model
import warnings
warnings.filterwarnings("ignore")

# ================================================
# 📂 2. Load the Data
# ================================================

# Not super large, so loading everything at once should be fine
train_df = pd.read_csv("/content/drive/MyDrive/dataset/train.csv")
test_df = pd.read_csv("/content/drive/MyDrive/dataset/test.csv")
train_audio_dir = "/content/drive/MyDrive/dataset/audios_train/"
test_audio_dir = "/content/drive/MyDrive/dataset/audios_test/"  # <-- adjust this if needed (mine was in a diff folder)

print(f"Loaded {len(train_df)} training samples.")
print(f"Loaded {len(test_df)} test samples.")

# ====================================
# 🎚️ 3. Feature Extraction
# ====================================

# Handcrafted Feature Extraction
def extract_audio_features(filepath, sr=16000):
    try:
        y, sr = librosa.load(filepath, sr=sr)

        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=20)
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        zcr = librosa.feature.zero_crossing_rate(y)
        rms = librosa.feature.rms(y=y)
        spectral_contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        tonnetz = librosa.feature.tonnetz(y=librosa.effects.harmonic(y), sr=sr)
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)

        features = [
            float(np.mean(mfccs)), float(np.std(mfccs)),
            float(np.mean(chroma)), float(np.std(chroma)),
            float(np.mean(zcr)), float(np.std(zcr)),
            float(np.mean(rms)), float(np.std(rms)),
            float(np.mean(spectral_contrast)), float(np.std(spectral_contrast)),
            float(np.mean(tonnetz)), float(np.std(tonnetz)),
            float(tempo)
        ]
        return features
    except:
        return [0.0] * 13


# Wav2Vec2 Feature Extractor
device = 'cuda' if torch.cuda.is_available() else 'cpu'
processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-base-960h")
model = Wav2Vec2Model.from_pretrained("facebook/wav2vec2-base-960h").to(device)


def extract_wav2vec_features(filepath):
    y, sr = librosa.load(filepath, sr=16000)
    input_values = processor(y, return_tensors="pt", sampling_rate=16000).input_values.to(device)
    with torch.no_grad():
        embeddings = model(input_values).last_hidden_state.mean(dim=1).cpu().numpy().flatten()
    return embeddings

# ====================================
# 🔁 4. Feature Collection
# ====================================
X_handcrafted, X_wav2vec, y = [], [], []

for _, row in train_df.iterrows():
    path = os.path.join(train_audio_dir, row["filename"])
    handcrafted_feat = extract_audio_features(path)
    wav2vec_feat = extract_wav2vec_features(path)

    X_handcrafted.append(handcrafted_feat)
    X_wav2vec.append(wav2vec_feat)
    y.append(row["label"])

X_handcrafted = np.array(X_handcrafted)
X_wav2vec = np.array(X_wav2vec)
y = np.array(y)

# ====================================
# 🧠 5. Model Training
# ====================================
Xh_train, Xh_val, Xw_train, Xw_val, y_train, y_val = train_test_split(
    X_handcrafted, X_wav2vec, y, test_size=0.2, random_state=42
)

# Handcrafted Feature Model
model_handcrafted = GradientBoostingRegressor()
model_handcrafted.fit(Xh_train, y_train)
pred_h = model_handcrafted.predict(Xh_val)

# Wav2Vec2 Feature Model
model_wav2vec = Ridge()
model_wav2vec.fit(Xw_train, y_train)
pred_w = model_wav2vec.predict(Xw_val)

# Final Ensemble Prediction (Weighted)
final_pred = 0.6 * pred_w + 0.4 * pred_h

# ===============================
# 🧠 Meta Model Training
# ===============================
X_meta_train = np.vstack([pred_h, pred_w]).T  # Use model outputs as features
y_meta_train = y_val                          # Target from validation

# Train the meta model
model_meta = Ridge()
model_meta.fit(X_meta_train, y_meta_train)

model_dir = "/content/drive/MyDrive/dataset/saved_models"

joblib.dump(model_handcrafted, os.path.join(model_dir, "model_handcrafted.pkl"))
joblib.dump(model_wav2vec, os.path.join(model_dir, "model_wav2vec.pkl"))
joblib.dump(model_meta, os.path.join(model_dir, "model_meta.pkl"))

print(f"✅ Models saved in '{model_dir}' directory!")

# ====================================
# 📊 6. Evaluation
# ====================================
print("Pearson Score:", pearsonr(y_val, final_pred)[0])
print("MSE:", mean_squared_error(y_val, final_pred))

model_handcrafted = joblib.load('/content/drive/MyDrive/dataset/saved_models/model_handcrafted.pkl')
model_wav2vec = joblib.load('/content/drive/MyDrive/dataset/saved_models/model_wav2vec.pkl')
model_meta = joblib.load('/content/drive/MyDrive/dataset/saved_models/model_meta.pkl')

# ================================================
# 📦 8. Inference on Test Set (Handcrafted + Wav2Vec2)
# ================================================

X_test_handcrafted, X_test_wav2vec = [], []

for _, row in test_df.iterrows():
    file_path = os.path.join(test_audio_dir, row["filename"])

    # Handcrafted Features
    handcrafted_feats = extract_audio_features(file_path)

    # Wav2Vec2 Features
    wav2vec_feats = extract_wav2vec_features(file_path)

    X_test_handcrafted.append(handcrafted_feats)
    X_test_wav2vec.append(wav2vec_feats)

# Convert to numpy arrays
X_test_handcrafted = np.array(X_test_handcrafted)
X_test_wav2vec = np.array(X_test_wav2vec)

# Predictions
test_preds_handcrafted = model_handcrafted.predict(X_test_handcrafted)
test_preds_wav2vec = model_wav2vec.predict(X_test_wav2vec)

# Meta Ensemble Predictions
X_test_meta = np.vstack([test_preds_handcrafted, test_preds_wav2vec]).T
final_test_preds = model_meta.predict(X_test_meta)

# Clip predictions between 0 and 5
final_test_preds = np.clip(final_test_preds, 0, 5)

# Save Submission
submission_df = pd.DataFrame({
    "filename": test_df["filename"],
    "label": final_test_preds
})

submission_df.to_csv("/content/drive/MyDrive/dataset/submission.csv", index=False)

print("\n✅ Submission saved as 'submission.csv'")

