import re
import os
import json
import time
from google.cloud import vision
from docx import Document
from docx.shared import Pt
import openai
from dotenv import load_dotenv
from flask import Flask, request, render_template, send_file, jsonify
from werkzeug.utils import secure_filename
from rapidfuzz import fuzz
from translators import translator_uzb, translator_kz, translator_usa, translator_ind, translator_china #type:ignore

# Загрузка API-ключей
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "outputs"
TEMPLATES_FOLDER = "templates_files"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Словарь для выбора нужного обработчика
TRANSLATORS = {
    "uzbekistan": translator_uzb,
    "india": translator_ind,
    "usa": translator_usa,
    "kazakhstan": translator_kz,
    "china": translator_china,
}

# Ключевые слова для определения страны
COUNTRY_KEYWORDS = {
    "uzbekistan": ["Republic of Uzbekistan", "O'zbekiston Respublikasi"],
    "india": ["Republic of India", "भारत गणराज्य"],
    "usa": [
        "United States of America",
        "USA",
        "The United States of America",
        "America",
    ],
    "kazakhstan": ["KAZ", "Republic of Kazakhstan", "ҚАЗАҚСТАН"],
    "china": ["REPUBLIC OF CHINA", "CHN", "China"],
}

def extract_text_with_vision_api(image_path):
    """Распознаёт текст с изображения с помощью Google Vision API."""
    print("\n🔍 Извлекаем текст с изображения...")
    client = vision.ImageAnnotatorClient()
    
    with open(image_path, 'rb') as image_file:
        content = image_file.read()
    image = vision.Image(content=content)

    response = client.text_detection(image=image)
    texts = response.text_annotations

    if not texts:
        print("❌ Текст не найден на изображении.")
        return ""

    extracted_text = texts[0].description.strip()
    print(f"✅ Извлечённый текст:\n{extracted_text[:500]}...")  # Показываем первые 500 символов
    return extracted_text


def detect_country_from_text(extracted_text):
    """Определяет страну по тексту паспорта с учетом неточностей."""
    extracted_text = extracted_text.lower()
    best_match = {"country": "unknown", "score": 0}

    for country, keywords in COUNTRY_KEYWORDS.items():
        for keyword in keywords:
            score = fuzz.partial_ratio(keyword.lower(), extracted_text)
            if score > best_match["score"]:
                best_match = {"country": country, "score": score}

    return best_match["country"] if best_match["score"] > 80 else "unknown"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "Файл не был загружен"}), 400

    file = request.files["file"]
    filename = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(file_path)

    base_filename = os.path.splitext(filename)[0]
    output_filename = f"{base_filename}.docx"
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)

    try:
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)

        # Универсальное извлечение текста (OCR), без привязки к translator_uzb
        extracted_text = extract_text_with_vision_api(file_path)
        if not extracted_text:
            return jsonify({"error": "Не удалось извлечь текст из файла"}), 500

        # Определение страны
        detected_country = detect_country_from_text(extracted_text)
        print(f"📌 Определена страна: {detected_country}")

        if detected_country not in TRANSLATORS:
            return jsonify({"error": "Страна не поддерживается или не определена"}), 400

        template_path = os.path.join(TEMPLATES_FOLDER, f"front_{detected_country}_template.docx")
        if not os.path.exists(template_path):
            return jsonify({"error": "Шаблон для страны не найден"}), 400

        TRANSLATORS[detected_country].process_document(file_path, template_path, output_path)


        if not os.path.exists(output_path):
            return jsonify({"error": "Ошибка: выходной файл не был создан"}), 500

        return send_file(output_path, as_attachment=True, download_name=output_filename)

    except Exception as e:
        return jsonify({"error": f"Ошибка обработки: {e}"}), 500

if __name__ == "__main__":
    app.run(debug=True)