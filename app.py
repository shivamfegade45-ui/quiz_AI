from flask import Flask, render_template, request, redirect, url_for, session
import os
import json
import random
import uuid

from pypdf import PdfReader
from werkzeug.utils import secure_filename
from openai import OpenAI


# =========================================================
# APP CONFIGURATION
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "quiz-secret-key-123"
)


# =========================================================
# NVIDIA NEMOTRON API
# =========================================================

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")

if not NVIDIA_API_KEY:
    raise RuntimeError(
        "NVIDIA_API_KEY is not set. "
        "Add NVIDIA_API_KEY in Render Environment Variables."
    )

client = OpenAI(
    base_url="https://integrate.api.nvidia.com/v1",
    api_key=NVIDIA_API_KEY
)

NEMOTRON_MODEL = "nvidia/nemotron-3-ultra-550b-a55b"


# =========================================================
# FOLDERS
# =========================================================

UPLOAD_FOLDER = "uploads"
QUIZ_DATA_FOLDER = "quiz_data"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(QUIZ_DATA_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


# =========================================================
# SETTINGS
# =========================================================

MAX_QUESTIONS = 100

ALLOWED_EXTENSIONS = {"pdf"}

VALID_TYPES = {
    "mcq",
    "fill_blank",
    "short_answer",
    "true_false",
    "match_pairs"
}

VALID_DIFFICULTIES = {
    "easy",
    "medium",
    "hard"
}


# =========================================================
# CHECK FILE
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
# CLEAN AI JSON
# =========================================================

def clean_json_response(content):

    if not content:
        return ""

    content = content.strip()

    # Remove Markdown code fences
    if content.startswith("```json"):
        content = content[7:].strip()

    elif content.startswith("```"):
        content = content[3:].strip()

    if content.endswith("```"):
        content = content[:-3].strip()

    # Sometimes AI adds text before/after JSON.
    # Try to isolate the JSON array.
    start = content.find("[")
    end = content.rfind("]")

    if start != -1 and end != -1 and end > start:
        content = content[start:end + 1]

    return content.strip()


# =========================================================
# NORMALIZE QUESTIONS
# =========================================================

def normalize_questions(
    questions,
    question_type,
    question_count
):

    if not isinstance(questions, list):

        raise ValueError(
            "AI did not return a question list."
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

        if not question_text:
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

            # Remove duplicates
            unique_options = []

            for option in options:

                if option.casefold() not in [
                    x.casefold()
                    for x in unique_options
                ]:
                    unique_options.append(option)

            if len(unique_options) < 4:
                continue

            options = unique_options[:4]

            matched_answer = None

            for option in options:

                if option.casefold() == answer.casefold():
                    matched_answer = option
                    break

            if not matched_answer:
                continue

            cleaned.append({
                "type": "mcq",
                "question": question_text,
                "options": options,
                "answer": matched_answer
            })


        # =================================================
        # FILL IN THE BLANK
        # =================================================

        elif question_type == "fill_blank":

            if not answer:
                continue

            cleaned.append({
                "type": "fill_blank",
                "question": question_text,
                "options": [],
                "answer": answer
            })


        # =================================================
        # SHORT ANSWER
        # =================================================

        elif question_type == "short_answer":

            if not answer:
                continue

            cleaned.append({
                "type": "short_answer",
                "question": question_text,
                "options": [],
                "answer": answer
            })


        # =================================================
        # TRUE / FALSE
        # =================================================

        elif question_type == "true_false":

            answer_lower = answer.casefold()

            if answer_lower not in {
                "true",
                "false"
            }:
                continue

            correct_answer = (
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
                "answer": correct_answer
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

            if len(cleaned_pairs) < 2:
                continue

            # Keep original correct mapping separately
            correct_pairs = list(cleaned_pairs)

            # Shuffle right-side choices
            right_options = [
                pair["right"]
                for pair in cleaned_pairs
            ]

            random.shuffle(right_options)

            cleaned.append({
                "type": "match_pairs",
                "question": question_text,
                "pairs": correct_pairs,
                "right_options": right_options,
                "answer": correct_pairs
            })


    if not cleaned:

        raise ValueError(
            "AI did not return usable questions. "
            "Please try again with a different topic, PDF, "
            "or smaller question count."
        )

    return cleaned[:question_count]


# =========================================================
# QUESTION GENERATOR
# =========================================================

def generate_ai_questions(
    topic,
    difficulty,
    question_type,
    question_count,
    pdf_text=""
):

    # Keep prompt reasonably sized
    MAX_PDF_CHARS = 100000

    pdf_content = ""

    if pdf_text:
        pdf_content = pdf_text[:MAX_PDF_CHARS]


    # =====================================================
    # SOURCE
    # =====================================================

    if pdf_content:

        source_instruction = f"""
The user uploaded a PDF.

Create questions ONLY from the information contained
in this PDF.

Do NOT use unrelated general knowledge.

PDF CONTENT:
-------------------------
{pdf_content}
-------------------------
"""

    else:

        source_instruction = f"""
No PDF was uploaded.

Create questions about this topic:

{topic}
"""


    # =====================================================
    # QUESTION TYPE
    # =====================================================

    if question_type == "mcq":

        type_instruction = """
QUESTION TYPE: MCQ

Rules:
- Every question must have exactly 4 options.
- Only one option is correct.
- The answer must exactly match one option.
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
    "answer": "Option 1"
  }
]
"""


    elif question_type == "fill_blank":

        type_instruction = """
QUESTION TYPE: FILL IN THE BLANK

Rules:
- Put ______ in every question.
- The answer must be the missing word or phrase.
"""

        json_format = """
[
  {
    "question": "The ______ is responsible for...",
    "options": [],
    "answer": "correct word"
  }
]
"""


    elif question_type == "short_answer":

        type_instruction = """
QUESTION TYPE: SHORT ANSWER

Rules:
- Ask a factual question.
- Answer should be short and clear.
"""

        json_format = """
[
  {
    "question": "What is ...?",
    "options": [],
    "answer": "Short correct answer"
  }
]
"""


    elif question_type == "true_false":

        type_instruction = """
QUESTION TYPE: TRUE / FALSE

Rules:
- Create factual statements.
- Do NOT create MCQs.
- Answer MUST be exactly True or False.
"""

        json_format = """
[
  {
    "question": "A factual statement.",
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
QUESTION TYPE: MATCH PAIRS

Rules:
- Create at least 4 pairs when enough source information exists.
- Each left item must have exactly one correct right item.
- Do not put the correct answer in a separate answer field.
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
    # PROMPT
    # =====================================================

    prompt = f"""
You are an expert educational quiz generator.

Generate exactly {question_count} questions.

Topic:
{topic}

Difficulty:
{difficulty}

{source_instruction}

{type_instruction}

IMPORTANT:

1. Generate exactly {question_count} questions.
2. Follow the requested question type exactly.
3. Do NOT generate MCQs when the requested type is True/False.
4. Do NOT mix question types.
5. If PDF content is provided, use ONLY the PDF.
6. Do not repeat questions.
7. Questions must be educational and accurate.
8. Return ONLY a valid JSON array.
9. Do not use Markdown.
10. Do not add explanations.
11. Use double quotes for JSON keys and strings.
12. Do not add trailing commas.
13. Start the response with [.
14. End the response with ].

JSON FORMAT:

{json_format}
"""


    # =====================================================
    # NVIDIA API CALL
    # =====================================================

    try:

        response = client.chat.completions.create(

            model=NEMOTRON_MODEL,

            messages=[
                {
                    "role": "system",
                    "content": (
                        "You generate educational quiz "
                        "questions and return valid JSON only."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            temperature=0.2,

            max_tokens=8000
        )

    except Exception as e:

        raise RuntimeError(
            f"NVIDIA API error: {e}"
        )


    # =====================================================
    # GET RESPONSE
    # =====================================================

    try:

        content = response.choices[0].message.content

    except Exception:

        content = None


    if not content:

        raise RuntimeError(
            "NVIDIA returned an empty response."
        )


    content = clean_json_response(
        content
    )


    # =====================================================
    # PARSE JSON
    # =====================================================

    try:

        questions = json.loads(
            content
        )

    except json.JSONDecodeError as e:

        print(
            "========== NVIDIA RAW RESPONSE =========="
        )

        print(content)

        print(
            "========================================="
        )

        raise RuntimeError(
            f"NVIDIA returned invalid JSON: {e}"
        )


    # =====================================================
    # NORMALIZE
    # =====================================================

    return normalize_questions(
        questions,
        question_type,
        question_count
    )


# =========================================================
# SAVE QUIZ
# =========================================================

def save_quiz_data(questions):

    quiz_id = str(uuid.uuid4())

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
# LOAD QUIZ
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

    except (
        ValueError,
        TypeError
    ):

        question_count = 5


    question_count = max(
        1,
        min(
            question_count,
            MAX_QUESTIONS
        )
    )


    # =====================================================
    # VALIDATE TYPE
    # =====================================================

    if question_type not in VALID_TYPES:

        question_type = "mcq"


    # =====================================================
    # VALIDATE DIFFICULTY
    # =====================================================

    if difficulty not in VALID_DIFFICULTIES:

        difficulty = "medium"


    # =====================================================
    # PDF
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

        # Unique filename prevents conflicts
        unique_filename = (
            f"{uuid.uuid4()}_{filename}"
        )

        pdf_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            unique_filename
        )


        try:

            uploaded_file.save(
                pdf_path
            )

            pdf_text = extract_pdf_text(
                pdf_path
            )

        except Exception as e:

            return (
                f"PDF ERROR: {e}",
                400
            )

        finally:

            # Remove uploaded PDF after extraction
            try:

                if os.path.exists(pdf_path):
                    os.remove(pdf_path)

            except Exception:
                pass


    # =====================================================
    # TOPIC
    # =====================================================

    if not topic:

        if pdf_text:

            topic = "Uploaded PDF"

        else:

            topic = "General Knowledge"


    # =====================================================
    # GENERATE
    # =====================================================

    try:

        questions = generate_ai_questions(

            topic=topic,

            difficulty=difficulty,

            question_type=question_type,

            question_count=question_count,

            pdf_text=pdf_text
        )

    except Exception as e:

        print(
            "NVIDIA ERROR:",
            e
        )

        error_message = str(e)

        error_template = os.path.join(
            "templates",
            "error.html"
        )

        if os.path.exists(error_template):

            return render_template(
                "error.html",
                error=error_message
            )

        return (
            f"""
            <h2>Quiz Generation Error</h2>
            <p>{error_message}</p>
            <p>Please try again.</p>
            """,
            500
        )


    # =====================================================
    # CHECK
    # =====================================================

    if not questions:

        return (
            "No questions were generated.",
            500
        )


    # =====================================================
    # SAVE
    # =====================================================

    quiz_id = save_quiz_data(
        questions
    )


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
    # CHECK QUESTIONS
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

        if question_type in {
            "mcq",
            "true_false",
            "fill_blank",
            "short_answer"
        }:

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


            # Normal comparison
            is_correct = (
                user_answer.casefold()
                == correct_answer.casefold()
            )


        # =================================================
        # MATCH PAIRS
        # =================================================

        elif question_type == "match_pairs":

            pairs = question.get(
                "pairs",
                []
            )

            is_correct = True

            user_answers = []

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

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
