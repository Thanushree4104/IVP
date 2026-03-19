from flask import Flask, request, render_template, send_file
import os
from services.watermark_service import process_embedding, process_extraction

app = Flask(__name__)

UPLOAD_FOLDER = "static/uploads"
OUTPUT_FOLDER = "static/outputs"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/embed', methods=['POST'])
def embed():
    file = request.files['image']
    watermark = request.form['watermark']

    input_path = os.path.join(UPLOAD_FOLDER, file.filename)
    output_path = os.path.join(OUTPUT_FOLDER, "watermarked_" + file.filename)

    file.save(input_path)

    output_file = process_embedding(input_path, output_path, watermark)
    return send_file(output_file, as_attachment=True)


@app.route('/extract', methods=['POST'])
def extract():
    file = request.files['image']
    length = int(request.form['length'])

    input_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(input_path)

    watermark = process_extraction(input_path, length)

    return render_template('index.html', extracted_text=watermark)


if __name__ == '__main__':
    app.run(debug=True)
