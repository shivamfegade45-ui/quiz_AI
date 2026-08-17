from flask import Flask, render_template, request, redirect, url_for, session
import os
import json
import random
import uuid
from pypdf import PdfReader
from werkzeug.utils import secure_filename
from google import genai


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)

app.secret_key = "quiz-secret-key-123"

# Gemini API
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. "
        "Set it in the terminal before running app.py."
    )

client = genai.Client(
    api_key=GEMINI_API_KEY
)


# =========================================================
# FOLDERS
# =========================================================

UPLOAD_FOLDER = "uploads"
QUIZ_DATA_FOLDER = "quiz_data"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QUIZ_DATA_FOLDER, exist_ok=True)


app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Maximum PDF size = 20 MB
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


# =========================================================
# SETTINGS
# =========================================================

MAX_QUESTIONS = 100

ALLOWED_EXTENSIONS = {
    "pdf"
}


# =========================================================
# HELPER - CHECK FILE
# =========================================================

def allowed_file(filename):

    if not filename:
        return False

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


# =========================================================
# PDF TEXT EXTRACTION
# =========================================================

def extract_pdf_text(pdf_path):

    text_parts = []

    try:

        reader = PdfReader(pdf_path)

        for page in reader.pages:

            page_text = page.extract_text()

            if page_text:
                text_parts.append(page_text)

    except Exception as e:

        raise RuntimeError(
            f"Unable to read PDF: {e}"
        )

    full_text = "\n".join(text_parts).strip()

    if not full_text:

        raise RuntimeError(
            "The PDF does not contain readable text."
        )

    return full_text


# =========================================================
# CLEAN GEMINI JSON
# =========================================================

def clean_json_response(content):

    content = content.strip()

    if content.startswith("```json"):

        content = content[7:]

    elif content.startswith("```"):

        content = content[3:]

    if content.endswith("```"):

        content = content[:-3]

    content = content.strip()

    return content


# =========================================================
# NORMALIZE QUESTION DATA
# =========================================================

def normalize_questions(
    questions,
    question_type,
    question_count
):

    if not isinstance(questions, list):

        raise ValueError(
            "Gemini did not return a question list."
        )

    cleaned = []

    for question in questions:

        if not isinstance(question, dict):
            continue

        question_text = str(
            question.get("question", "")
        ).strip()

        answer = str(
            question.get("answer", "")
        ).strip()

        if not question_text or not answer:
            continue


        # =================================================
        # MCQ
        # =================================================

        if question_type == "mcq":

            options = question.get(
                "options",
                []
            )

            if not isinstance(options, list):
                continue

            options = [
                str(option).strip()
                for option in options
                if str(option).strip()
            ]

            if len(options) < 4:
                continue

            options = options[:4]

            if answer not in options:

                # Try case-insensitive matching
                matched = None

                for option in options:

                    if option.casefold() == answer.casefold():

                        matched = option
                        break

                if matched:
                    answer = matched

                else:
                    continue

            cleaned.append({
                "type": "mcq",
                "question": question_text,
                "options": options,
                "answer": answer
            })


        # =================================================
        # FILL BLANK
        # =================================================

        elif question_type == "fill_blank":

            cleaned.append({
                "type": "fill_blank",
                "question": question_text,
                "answer": answer
            })


        # =================================================
        # SHORT ANSWER
        # =================================================

        elif question_type == "short_answer":

            cleaned.append({
                "type": "short_answer",
                "question": question_text,
                "answer": answer
            })


        # =================================================
        # TRUE / FALSE
        # =================================================

        elif question_type == "true_false":

            answer_lower = answer.casefold()

            if answer_lower in [
                "true",
                "false"
            ]:

                answer = (
                    "True"
                    if answer_lower == "true"
                    else "False"
                )

                cleaned.append({
                    "type": "true_false",
                    "question": question_text,
                    "options": [
                        "True",
                        "False"
                    ],
                    "answer": answer
                })


        # =================================================
        # MATCH PAIRS
        # =================================================

        elif question_type == "match_pairs":

            pairs = question.get(
                "pairs",
                []
            )

            if not isinstance(pairs, list):
                continue

            cleaned_pairs = []

            for pair in pairs:

                if not isinstance(pair, dict):
                    continue

                left = str(
                    pair.get("left", "")
                ).strip()

                right = str(
                    pair.get("right", "")
                ).strip()

                if left and right:

                    cleaned_pairs.append({
                        "left": left,
                        "right": right
                    })

            if len(cleaned_pairs) >= 2:

                random.shuffle(cleaned_pairs)

                cleaned.append({
                    "type": "match_pairs",
                    "question": question_text,
                    "pairs": cleaned_pairs,
                    "answer": cleaned_pairs
                })


    if not cleaned:

        raise ValueError(
            "Gemini did not return usable questions."
        )


    # Do not exceed requested count
    cleaned = cleaned[:question_count]

    return cleaned


# =========================================================
# GEMINI QUESTION GENERATOR
# =========================================================

def generate_ai_questions(
    topic,
    difficulty,
    question_type,
    question_count,
    pdf_text=""
):

    # Limit PDF text to a reasonable size
    # This prevents extremely large prompts.
    MAX_PDF_CHARS = 300000

    if pdf_text:

        pdf_content = pdf_text[
            :MAX_PDF_CHARS
        ]

    else:

        pdf_content = ""


    # =====================================================
    # SOURCE INSTRUCTION
    # =====================================================

    if pdf_content:

        source_instruction = f"""
The user uploaded a PDF.

You MUST create the questions from the PDF content below.

Do NOT create unrelated General Knowledge questions.

If the PDF is about Biology, create Biology questions
from the actual PDF content.

PDF CONTENT:
----------------
{pdf_content}
----------------
"""

    else:

        source_instruction = f"""
No PDF was uploaded.

Create questions based on the requested topic:

{topic}
"""


    # =====================================================
    # QUESTION TYPE INSTRUCTIONS
    # =====================================================

    if question_type == "mcq":

        type_instruction = """
Question type: MCQ

Rules:
- Exactly 4 options for every question.
- Exactly one correct answer.
"""

        json_format = """
[
  {
    "question": "Question text",
    "options": [
      "Option 1",
      "Option 2",
      "Option 3",
      "Option 4"
    ],
    "answer": "Correct option"
  }
]
"""


    elif question_type == "fill_blank":

        type_instruction = """
Question type: Fill in the blanks

Rules:
- Each question must contain a blank such as ______.
- The answer must be the missing word or phrase.
"""

        json_format = """
[
  {
    "question": "The process of ______ occurs in plants.",
    "options": [],
    "answer": "photosynthesis"
  }
]
"""


    elif question_type == "short_answer":

        type_instruction = """
Question type: Short Answer

Rules:
- Ask questions requiring a short factual answer.
- Keep answers concise.
"""

        json_format = """
[
  {
    "question": "What is photosynthesis?",
    "options": [],
    "answer": "The process by which plants make food using light energy."
  }
]
"""


    elif question_type == "true_false":

        type_instruction = """
Question type: True / False

Rules:
- The question must be a factual statement.
- The answer MUST be exactly True or False.
"""

        json_format = """
[
  {
    "question": "Photosynthesis occurs in plants.",
    "options": [
      "True",
      "False"
    ],
    "answer": "True"
  }
]
"""


    elif question_type == "match_pairs":

        type_instruction = """
Question type: Match Pairs

Rules:
- Create matching pairs based on the source material.
- Create at least 4 pairs when enough information is available.
"""

        json_format = """
[
  {
    "question": "Match the following:",
    "pairs": [
      {
        "left": "Term 1",
        "right": "Definition 1"
      },
      {
        "left": "Term 2",
        "right": "Definition 2"
      },
      {
        "left": "Term 3",
        "right": "Definition 3"
      },
      {
        "left": "Term 4",
        "right": "Definition 4"
      }
    ],
    "answer": "matching pairs"
  }
]
"""


    else:

        raise ValueError(
            "Invalid question type."
        )


    # =====================================================
    # FINAL PROMPT
    # =====================================================

    prompt = f"""
You are an expert educational quiz generator.

Create exactly {question_count} quiz questions.

Topic:
{topic}

Difficulty:
{difficulty}

{source_instruction}

{type_instruction}

IMPORTANT RULES:

1. Generate exactly {question_count} questions.
2. Do not generate General Knowledge questions unless the requested topic itself is General Knowledge.
3. If a PDF is supplied, use the PDF as the primary source.
4. Questions must be relevant to the source material.
5. Do not repeat questions.
6. Do not add explanations outside JSON.
7. Return ONLY valid JSON.
8. Do not use Markdown code fences.
9. Keep the language of the questions clear and educational.

JSON FORMAT:
{json_format}
"""


    # =====================================================
    # GEMINI API CALL
    # =====================================================

    response = client.models.generate_content(

        model="gemini-3.6-flash",

        contents=prompt,

        config={
            "temperature": 0.7,
            "response_mime_type": "application/json"
        }
    )


    content = response.text

    if not content:

        raise RuntimeError(
            "Gemini returned an empty response."
        )


    content = clean_json_response(
        content
    )


    try:

        questions = json.loads(
            content
        )

    except json.JSONDecodeError as e:

        print(
            "Gemini JSON ERROR:",
            content
        )

        raise RuntimeError(
            f"Gemini returned invalid JSON: {e}"
        )


    return normalize_questions(
        questions,
        question_type,
        question_count
    )


# =========================================================
# SAVE QUIZ DATA
# =========================================================

def save_quiz_data(questions):

    quiz_id = str(
        uuid.uuid4()
    )

    file_path = os.path.join(
        QUIZ_DATA_FOLDER,
        f"{quiz_id}.json"
    )

    with open(
        file_path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            questions,
            file,
            ensure_ascii=False,
            indent=2
        )

    return quiz_id


# =========================================================
# LOAD QUIZ DATA
# =========================================================

def load_quiz_data(quiz_id):

    if not quiz_id:
        return []

    file_path = os.path.join(
        QUIZ_DATA_FOLDER,
        f"{quiz_id}.json"
    )

    if not os.path.exists(file_path):
        return []

    try:

        with open(
            file_path,
            "r",
            encoding="utf-8"
        ) as file:

            return json.load(file)

    except Exception:

        return []


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# GENERATE QUIZ
# =========================================================

@app.route(
    "/generate",
    methods=["POST"]
)
def generate():

    # =====================================================
    # FORM DATA
    # =====================================================

    topic = request.form.get(
        "topic",
        ""
    ).strip()

    difficulty = request.form.get(
        "difficulty",
        "medium"
    ).strip().lower()

    question_type = request.form.get(
        "question_type",
        "mcq"
    ).strip().lower()


    # =====================================================
    # QUESTION COUNT
    # =====================================================

    try:

        question_count = int(
            request.form.get(
                "num_questions",
                request.form.get(
                    "question_count",
                    "5"
                )
            )
        )

    except (ValueError, TypeError):

        question_count = 5


    if question_count < 1:

        question_count = 5


    if question_count > MAX_QUESTIONS:

        question_count = MAX_QUESTIONS


    # =====================================================
    # VALIDATE QUESTION TYPE
    # =====================================================

    valid_types = [
        "mcq",
        "fill_blank",
        "short_answer",
        "true_false",
        "match_pairs"
    ]

    if question_type not in valid_types:

        question_type = "mcq"


    # =====================================================
    # VALIDATE DIFFICULTY
    # =====================================================

    valid_difficulties = [
        "easy",
        "medium",
        "hard"
    ]

    if difficulty not in valid_difficulties:

        difficulty = "medium"


    # =====================================================
    # PDF UPLOAD
    # =====================================================

    pdf_text = ""

    uploaded_file = request.files.get(
        "file"
    )


    if uploaded_file and uploaded_file.filename:

        if not allowed_file(
            uploaded_file.filename
        ):

            return (
                "Only PDF files are supported.",
                400
            )


        filename = secure_filename(
            uploaded_file.filename
        )


        pdf_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
        )


        uploaded_file.save(
            pdf_path
        )


        try:

            pdf_text = extract_pdf_text(
                pdf_path
            )

        except Exception as e:

            return (
                f"PDF ERROR: {e}",
                400
            )


    # =====================================================
    # TOPIC
    # =====================================================

    if not topic:

        if pdf_text:

            topic = "Uploaded PDF"

        else:

            topic = "General Knowledge"


    # =====================================================
    # GENERATE WITH GEMINI
    # =====================================================

    try:

        questions = generate_ai_questions(

            topic,

            difficulty,

            question_type,

            question_count,

            pdf_text
        )


    except Exception as e:

        print(
            "GEMINI ERROR:",
            e
        )

        return render_template(
            "error.html",
            error=str(e)
        ) if os.path.exists(
            os.path.join(
                "templates",
                "error.html"
            )
        ) else (
            f"""
            <h2>Quiz Generation Error</h2>
            <p>{str(e)}</p>
            <p>Please check your Gemini API key and try again.</p>
            """,
            500
        )


    # =====================================================
    # VERIFY QUESTION COUNT
    # =====================================================

    if not questions:

        return (
            "No questions were generated.",
            500
        )


    # =====================================================
    # SAVE QUESTIONS SERVER-SIDE
    # =====================================================

    quiz_id = save_quiz_data(
        questions
    )


    # Only small values go into Flask session
    session["quiz_id"] = quiz_id
    session["topic"] = topic
    session["difficulty"] = difficulty
    session["question_type"] = question_type


    # =====================================================
    # SHOW QUIZ
    # =====================================================

    return render_template(

        "quiz.html",

        questions=questions,

        topic=topic,

        difficulty=difficulty,

        question_type=question_type
    )


# =========================================================
# SUBMIT QUIZ
# =========================================================

@app.route(
    "/submit",
    methods=["POST"]
)
def submit():

    quiz_id = session.get(
        "quiz_id"
    )


    questions = load_quiz_data(
        quiz_id
    )


    if not questions:

        return redirect(
            url_for("home")
        )


    score = 0

    results = []


    # =====================================================
    # CHECK EACH QUESTION
    # =====================================================

    for index, question in enumerate(
        questions
    ):

        question_type = question.get(
            "type",
            "mcq"
        )


        user_answer = ""

        correct_answer = ""

        is_correct = False


        # =================================================
        # MCQ / TRUE FALSE / FILL / SHORT
        # =================================================

        if question_type in [

            "mcq",

            "true_false",

            "fill_blank",

            "short_answer"

        ]:

            user_answer = request.form.get(

                f"question_{index}",

                ""

            ).strip()


            correct_answer = str(

                question.get(

                    "answer",

                    ""

                )

            ).strip()


            # Case-insensitive comparison
            is_correct = (

                user_answer.casefold()

                == correct_answer.casefold()

            )


        # =================================================
        # MATCH PAIRS
        # =================================================

        elif question_type == "match_pairs":

            is_correct = True

            user_answers = []


            pairs = question.get(

                "pairs",

                []

            )


            for pair_index, pair in enumerate(

                pairs

            ):

                selected_answer = request.form.get(

                    f"question_{index}_pair_{pair_index}",

                    ""

                ).strip()


                user_answers.append(

                    selected_answer

                )


                correct_pair_answer = str(

                    pair.get(

                        "right",

                        ""

                    )

                ).strip()


                if (

                    selected_answer.casefold()

                    != correct_pair_answer.casefold()

                ):

                    is_correct = False


            user_answer = ", ".join(

                user_answers

            )


            correct_answer = ", ".join(

                str(

                    pair.get(

                        "right",

                        ""

                    )

                )

                for pair in pairs

            )


        # =================================================
        # SCORE
        # =================================================

        if is_correct:

            score += 1


        # =================================================
        # RESULT
        # =================================================

        results.append({

            "question": question.get(

                "question",

                ""

            ),

            "user_answer": user_answer,

            "correct_answer": correct_answer,

            "is_correct": is_correct

        })


    # =====================================================
    # RESULT PAGE
    # =====================================================

    return render_template(

        "result.html",

        score=score,

        total=len(questions),

        results=results

    )


# =========================================================
# RUN APPLICATION
# =========================================================

if __name__ == "__main__":

    app.run(

        host="127.0.0.1",

        port=5000,

        debug=True

    )