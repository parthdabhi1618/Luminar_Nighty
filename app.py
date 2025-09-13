from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_wtf.csrf import CSRFProtect
import fitz
import os
import tempfile
import re
import subprocess
import html
from werkzeug.utils import secure_filename

# ReportLab Imports
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Frame, PageTemplate, Preformatted, Image
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from io import BytesIO
from reportlab.pdfgen import canvas

# Pygments for Syntax Highlighting & Matplotlib for LaTeX
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter
import matplotlib.pyplot as plt

app = Flask(__name__)
temp_dir = tempfile.mkdtemp()
app.config['UPLOAD_FOLDER'] = temp_dir
app.config['SECRET_KEY'] = 'luminar-secret-key-2025'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
plt.switch_backend('agg')
csrf = CSRFProtect(app)

# --- PDF Generation Color Palette ---
dark_bg = colors.HexColor("#0A0A0A")
white_text = colors.HexColor("#FFFFFF")
green_accent = colors.HexColor("#00FF41")
cyan_accent = colors.HexColor("#00D4FF")

# --- Feature 1: Highlight Extraction (Function is unchanged) ---
def extract_highlights(pdf_path):
    # ... no changes to this function ...
    doc = fitz.open(pdf_path)
    highlights = []
    for page in doc:
        for annot in page.annots():
            if annot.type[1] == "Highlight":
                rect = annot.rect; words = page.get_text("words", clip=rect)
                if not words: continue
                lines = {}
                for word in words:
                    y_pos = round(word[3], 1)
                    if y_pos not in lines: lines[y_pos] = []
                    lines[y_pos].append(word[4])
                for y_pos in sorted(lines.keys()):
                    line_text = ' '.join(lines[y_pos]).strip()
                    if not line_text: continue
                    if re.match(r'^(AIM:|Objective:|Goal:)', line_text, re.IGNORECASE):
                        highlights.append(('heading', line_text))
                    elif re.search(r'\b(def|class|public|static|void|int|String|import|from)\b', line_text) and any(c in line_text for c in '{}();='):
                         highlights.append(('code', line_text))
                    elif re.search(r'[\^=\+\-\*\/]', line_text) and len(line_text) < 100:
                        highlights.append(('math', line_text))
                    else: highlights.append(('point', line_text))
    return highlights

# --- Advanced PDF Creation for Highlights ---
def create_matrix_pdf(highlights, output_path):
    # Define margins
    left_margin, right_margin, top_margin, bottom_margin = (0.75*inch,) * 4

    # Page template function to draw background and static elements
    def page_template(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(dark_bg)
        canvas.rect(0, 0, letter[0], letter[1], fill=1)
        canvas.setFillColor(green_accent)
        canvas.setFont('Helvetica-Bold', 10)
        canvas.drawCentredString(letter[0]/2, letter[1] - 0.5*inch, "Luminar Notes")
        canvas.setFillColor(cyan_accent)
        canvas.setFont('Helvetica', 9)
        canvas.drawCentredString(letter[0]/2, 0.5*inch, f"Page {doc.page}")
        canvas.restoreState()

    # FIXED: Initialize Doc, then define Frame and Template, then add Template to Doc
    doc = SimpleDocTemplate(output_path, pagesize=letter,
                            leftMargin=left_margin, rightMargin=right_margin,
                            topMargin=top_margin, bottomMargin=bottom_margin)
                            
    content_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='content_frame')
    template = PageTemplate(id='main', frames=[content_frame], onPage=page_template)
    doc.addPageTemplates([template])
    
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='MatrixHeading', fontName='Helvetica-Bold', fontSize=16, textColor=green_accent, alignment=TA_CENTER, spaceAfter=12, leading=22))
    styles.add(ParagraphStyle(name='MatrixBody', fontName='Helvetica', fontSize=12, textColor=white_text, spaceAfter=8, leading=18))
    styles.add(ParagraphStyle(name='MatrixCode', fontName='Courier', fontSize=11, textColor=white_text, backColor=colors.HexColor("#1A1A1A"), borderPadding=5, leading=14))
    
    story = []; toc = TableOfContents(); toc.levelStyles = [ParagraphStyle(name='TOC_L1', textColor=green_accent, fontName='Helvetica-Bold')]; story.append(toc)
    
    for item_type, text in highlights:
        if item_type == 'heading':
            p = Paragraph(text.upper(), styles['MatrixHeading']); p.bookmarkKey = text.lower().replace(" ", "_"); story.append(p)
        elif item_type == 'code':
            p = Preformatted(text, styles['MatrixCode']); story.append(p)
        elif item_type == 'math':
            try:
                fig = plt.figure(figsize=(6, 1), facecolor='#0A0A0A'); fig.text(0.5, 0.5, f'${text}$', ha='center', va='center', fontsize=20, color='white')
                img_path = os.path.join(temp_dir, f'math_{hash(text)}.png'); plt.savefig(img_path, transparent=True, bbox_inches='tight', pad_inches=0.1); plt.close(fig)
                story.append(Image(img_path, width=4*inch, height=0.5*inch))
            except Exception: story.append(Paragraph(text, styles['MatrixBody']))
        else:
            p_text = f'<bullet color="{cyan_accent.hexval()}">•</bullet> {html.escape(text)}'
            story.append(Paragraph(p_text, styles['MatrixBody']))
        story.append(Spacer(1, 12))
    doc.build(story)

# --- Feature 2: Header & Footer Adder (Function is unchanged) ---
def add_header_footer_to_pdf(input_pdf_path, output_filepath, headers, footers, start_page_num, page_num_placement):
    # ... no changes to this function ...
    input_doc = fitz.open(input_pdf_path); output_doc = fitz.open(); margin = 0.5 * inch
    page_num_area, page_num_pos = page_num_placement.split('-')
    for i, page in enumerate(input_doc):
        new_page = output_doc.new_page(width=page.rect.width, height=page.rect.height)
        packet = BytesIO(); can = canvas.Canvas(packet, pagesize=(page.rect.width, page.rect.height)); can.setFont('Helvetica', 9)
        can.drawString(margin, page.rect.height - margin + 10, headers.get('left', ''))
        can.drawCentredString(page.rect.width / 2, page.rect.height - margin + 10, headers.get('center', ''))
        can.drawRightString(page.rect.width - margin, page.rect.height - margin + 10, headers.get('right', ''))
        can.drawString(margin, margin - 10, footers.get('left', ''))
        can.drawCentredString(page.rect.width / 2, margin - 10, footers.get('center', ''))
        can.drawRightString(page.rect.width - margin, margin - 10, footers.get('right', ''))
        page_num_str = str(start_page_num + i)
        y_pos = page.rect.height - margin + 10 if page_num_area == 'header' else margin - 10
        if page_num_pos == 'left': can.drawString(margin, y_pos, page_num_str)
        elif page_num_pos == 'right': can.drawRightString(page.rect.width - margin, y_pos, page_num_str)
        else: can.drawCentredString(page.rect.width / 2, y_pos, page_num_str)
        can.save(); packet.seek(0)
        overlay_doc = fitz.open("pdf", packet.read()); new_page.show_pdf_page(new_page.rect, overlay_doc, 0)
        content_rect = fitz.Rect(margin / 2, margin, page.rect.width - (margin / 2), page.rect.height - margin)
        new_page.show_pdf_page(content_rect, input_doc, i)
    output_doc.save(output_filepath); output_doc.close(); input_doc.close()

# --- Flask Routes (No changes) ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/temp/<path:filename>')
def serve_temp_file(filename):
    return send_from_directory(temp_dir, filename, as_attachment=False)

@csrf.exempt
@app.route('/extract_highlights', methods=['POST'])
def extract_highlights_route():
    if 'file' not in request.files: return jsonify({'error': 'No file part'}), 400
    file = request.files['file'];
    if not file or file.filename == '' or not file.filename.lower().endswith('.pdf'): return jsonify({'error': 'Invalid or no file selected'}), 400
    filename = secure_filename(file.filename); filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename); file.save(filepath)
    try:
        highlights = extract_highlights(filepath)
        if not highlights: return jsonify({'error': 'No highlights were found in the PDF.'}), 400
        output_filename = filename.replace('.pdf', '_notes.pdf'); output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        create_matrix_pdf(highlights, output_filepath)
        return jsonify({'previewUrl': f'/temp/{output_filename}'})
    except Exception as e:
        print(f"Error during highlight extraction: {e}"); return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500
    finally:
        if os.path.exists(filepath): os.remove(filepath)

@csrf.exempt
@app.route('/add_header_footer', methods=['POST'])
def add_header_footer_route():
    if 'file' not in request.files: return jsonify({'error': 'No file part'}), 400
    file = request.files['file']; form_data = request.form
    allowed_extensions = ['.pdf', '.ipynb'];
    if not file or file.filename == '' or not any(file.filename.lower().endswith(ext) for ext in allowed_extensions): return jsonify({'error': 'Invalid file type.'}), 400
    input_filename = secure_filename(file.filename); input_filepath = os.path.join(app.config['UPLOAD_FOLDER'], input_filename); file.save(input_filepath)
    intermediate_pdf_path = input_filepath
    if input_filename.lower().endswith('.ipynb'):
        try:
            pdf_output_path = os.path.splitext(input_filepath)[0] + '.pdf'
            subprocess.run(['jupyter', 'nbconvert', '--to', 'webpdf', '--allow-chromium-download', input_filepath], check=True, timeout=60)
            intermediate_pdf_path = pdf_output_path
        except Exception as e: return jsonify({'error': f'IPYNB conversion failed. Error: {e}'}), 500
    headers = {'left': form_data.get('headerLeft', ''), 'center': form_data.get('headerCenter', ''), 'right': form_data.get('headerRight', '')}
    footers = {'left': form_data.get('footerLeft', ''), 'center': form_data.get('footerCenter', ''), 'right': form_data.get('footerRight', '')}
    page_num_placement = form_data.get('pageNumPlacement', 'footer-center')
    try: start_page_num = int(form_data.get('startPageNum', 1))
    except (ValueError, TypeError): start_page_num = 1
    output_filename = os.path.basename(intermediate_pdf_path).replace('.pdf', '_formatted.pdf'); output_filepath = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
    try:
        add_header_footer_to_pdf(intermediate_pdf_path, output_filepath, headers, footers, start_page_num, page_num_placement)
        return jsonify({'previewUrl': f'/temp/{output_filename}'})
    except Exception as e:
        print(f"Error during H&F addition: {e}"); return jsonify({'error': f'Failed to process PDF: {str(e)}'}), 500
    finally: pass

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

application = app
