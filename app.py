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
    "FLASK_SECRET_KEY",
    "quiz-secret-key-123"
)


# =========================================================
# NVIDIA NEMOTRON API
# =========================================================

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")

if not NVIDIA_API_KEY:
    raise RuntimeError(
        "NVIDIA_API_KEY is not set. "
        "Add NVIDIA_API_KEY in your environment variables."
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

# Maximum PDF size = 20 MB
app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


# =========================================================
# SETTINGS
# =========================================================

MAX_QUESTIONS = 100

ALLOWED_EXTENSIONS = {"pdf"}


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
# CLEAN AI RESPONSE
# =========================================================

def clean_json_response(content):

    if not content:
        return ""

    content = content.strip()

    # Remove markdown fences
    if content.startswith("```json"):

        content = content[7:]

    elif content.startswith("```"):

        content = content[3:]

    if content.endswith("```"):

        content = content[:-3]

    content = content.strip()

    # Sometimes model adds text before/after JSON.
    # Try to keep only the JSON array.

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
            "Nemotron did not return a question list."
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


        # =====================================================
        # MCQ
        # =====================================================

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

            # Remove duplicate options
            unique_options = []

            for option in options:

                if option.casefold() not in [
                    x.casefold()
                    for x in unique_options
                ]:

                    unique_options.append(option)

            options = unique_options

            if len(options) < 4:
                continue

            options = options[:4]

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


        # =====================================================
        # TRUE / FALSE
        # =====================================================

        elif question_type == "true_false":

            answer_lower = answer.casefold()

            if answer_lower not in [
                "true",
                "false"
            ]:

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


        # =====================================================
        # FILL BLANK
        # =====================================================

        elif question_type == "fill_blank":

            if not answer:
                continue

            cleaned.append({
                "type": "fill_blank",
                "question": question_text,
                "answer": answer
            })


        # =====================================================
        # SHORT ANSWER
        # =====================================================

        elif question_type == "short_answer":

            if not answer:
                continue

            cleaned.append({
                "type": "short_answer",
                "question": question_text,
                "answer": answer
            })


        # =====================================================
        # MATCH PAIRS
        # =====================================================

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

            # Shuffle only the displayed right-side choices
            rights = [
                pair["right"]
                for pair in cleaned_pairs
            ]

            random.shuffle(rights)

            cleaned.append({
                "type": "match_pairs",
                "question": question_text,
                "pairs": cleaned_pairs,
                "options": rights
            })


    if not cleaned:

        raise ValueError(
            "Nemotron did not return usable questions. "
            "Try a smaller question count or another topic/PDF."
        )

    return cleaned[:question_count]


# =========================================================
# GENERATE AI QUESTIONS
# =========================================================

def generate_ai_questions(
    topic,
    difficulty,
    question_type,
    question_count,
    pdf_text=""
):

    # Keep prompt reasonably sized.
    MAX_PDF_CHARS = 60000

    if pdf_text:

        pdf_content = pdf_text[
            :MAX_PDF_CHARS
        ]

    else:

        pdf_content = ""


    # =====================================================
    # SOURCE
    # =====================================================

    if pdf_content:

        source_instruction = f"""
The user uploaded a PDF.

IMPORTANT:
Create questions ONLY from the information contained
in this PDF.

Do not use unrelated general knowledge.

PDF CONTENT:
----------------
{pdf_content}
----------------
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

For every question:
- Give exactly 4 options.
- Only one option must be correct.
- The answer must exactly match one option.
"""


    elif question_type == "true_false":

        type_instruction = """
QUESTION TYPE: TRUE / FALSE

For every question:
- Write a factual statement.
- The answer MUST be exactly True or False.
- Do not use any other answer.
"""


    elif question_type == "fill_blank":

        type_instruction = """
QUESTION TYPE: FILL IN THE BLANK

For every question:
- Include ______ in the sentence.
- The answer must be the missing word or phrase.
"""


    elif question_type == "short_answer":

        type_instruction = """
QUESTION TYPE: SHORT ANSWER

For every question:
- Ask a factual question.
- Give a concise correct answer.
"""


    elif question_type == "match_pairs":

        type_instruction = """
QUESTION TYPE: MATCH PAIRS

For every question:
- Create at least 4 pairs when enough information exists.
- Each pair must contain a left term and a right definition.
"""


    else:

        raise ValueError(
            "Invalid question type."
        )


    # =====================================================
    # JSON FORMAT
    # =====================================================

    if question_type == "mcq":

        json_format = """
[
  {
    "question": "Question",
    "options": [
      "Option A",
      "Option B",
      "Option C",
      "Option D"
    ],
    "answer": "Option A"
  }
]
"""


    elif question_type == "true_false":

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


    elif question_type == "fill_blank":

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

        json_format = """
[
  {
    "question": "What is photosynthesis?",
    "options": [],
    "answer": "It is the process by which plants make food."
  }
]
"""


    else:

        json_format = """
[
  {
    "question": "Match the following.",
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
    "options": []
  }
]
"""


    # =====================================================
    # PROMPT
    # =====================================================

    prompt = f"""
You are an expert educational quiz generator.

Generate exactly {question_count} questions.

TOPIC:
{topic}

DIFFICULTY:
{difficulty}

{source_instruction}

{type_instruction}

STRICT RULES:

1. Generate exactly {question_count} questions.
2. Follow the requested question type exactly.
3. If a PDF is supplied, use ONLY information from the PDF.
4. Do not invent information not supported by the PDF.
5. Do not repeat questions.
6. Questions must be educational and accurate.
7. Return ONLY one JSON array.
8. Do not use Markdown.
9. Do not add explanations.
10. Use double quotes for JSON keys and strings.
11. Do not use trailing commas.
12. Do not put comments inside JSON.
13. Do not add text before or after the JSON array.

EXPECTED JSON FORMAT:

{json_format}
"""


    # =====================================================
    # NVIDIA API
    # =====================================================

    try:

        response = client.chat.completions.create(

            model=NEMOTRON_MODEL,

            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            temperature=0.2,

            max_tokens=12000,

            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": False
                }
            }
        )

    except Exception as e:

        raise RuntimeError(
            f"NVIDIA API error: {e}"
        )


    # =====================================================
    # RESPONSE
    # =====================================================

    if not response.choices:

        raise RuntimeError(
            "NVIDIA returned no response choices."
        )

    content = response.choices[0].message.content

    if not content:

        raise RuntimeError(
            "Nemotron returned an empty response."
        )

    content = clean_json_response(
        content
    )


    # =====================================================
    # JSON PARSE
    # =====================================================

    try:

        questions = json.loads(
            content
        )

    except json.JSONDecodeError as e:

        print(
            "\n========== NEMOTRON RAW RESPONSE =========="
        )

        print(content)

        print(
            "============================================\n"
        )

        raise RuntimeError(
            f"Nemotron returned invalid JSON: {e}"
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


    question_count = max(
        1,
        min(question_count, MAX_QUESTIONS)
    )


    # =====================================================
    # VALID QUESTION TYPES
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
    # VALID DIFFICULTIES
    # =====================================================

    valid_difficulties = [
        "easy",
        "medium",
        "hard"
    ]

    if difficulty not in valid_difficulties:

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

        # Avoid problems with duplicate filenames
        filename = (
            f"{uuid.uuid4().hex}_"
            f"{filename}"
        )

        pdf_path = os.path.join(
            app.config["UPLOAD_FOLDER"],
            filename
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

        error_html = f"""
        <h2>Quiz Generation Error</h2>
        <p>{str(e)}</p>
        <br>
        <a href="/">Go Back</a>
        """

        return (
            error_html,
            500
        )


    # =====================================================
    # CHECK QUESTIONS
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


    # =====================================================
    # SESSION
    # =====================================================

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
        # MCQ / TRUE FALSE
        # =================================================

        if question_type in [
            "mcq",
            "true_false"
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

            is_correct = (
                user_answer.casefold()
                == correct_answer.casefold()
            )


        # =================================================
        # FILL BLANK / SHORT ANSWER
        # =================================================

        elif question_type in [
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

            # Exact answer first
            is_correct = (
                user_answer.casefold()
                == correct_answer.casefold()
            )

            # For short answers, allow the expected answer
            # to be contained in the user's answer.
            if (
                not is_correct
                and question_type == "short_answer"
                and user_answer
                and correct_answer
            ):

                is_correct = (
                    correct_answer.casefold()
                    in user_answer.casefold()
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

            correct_answers = []


            for pair_index, pair in enumerate(
                pairs
            ):

                selected_answer = request.form.get(
                    f"question_{index}_pair_{pair_index}",
                    ""
                ).strip()

                correct_pair_answer = str(
                    pair.get(
                        "right",
                        ""
                    )
                ).strip()

                user_answers.append(
                    selected_answer
                )

                correct_answers.append(
                    correct_pair_answer
                )

                if (
                    selected_answer.casefold()
                    != correct_pair_answer.casefold()
                ):

                    is_correct = False


            user_answer = ", ".join(
                user_answers
            )

            correct_answer = ", ".join(
                correct_answers
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
````
