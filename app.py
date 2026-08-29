from flask import Flask, render_template, request, redirect, url_for, session
import os
import json
import random
import uuid
import re

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

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024


# =========================================================
# NVIDIA NEMOTRON API
# =========================================================

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY")

if not NVIDIA_API_KEY:
    raise RuntimeError(
        "NVIDIA_API_KEY is not set. "
        "Please add NVIDIA_API_KEY in Render Environment Variables."
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


# =========================================================
# SETTINGS
# =========================================================

MAX_QUESTIONS = 100

ALLOWED_EXTENSIONS = {
    "pdf"
}


# =========================================================
# ALLOWED FILE
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

def clean_ai_response(content):

    if not content:
        return ""

    content = str(content).strip()

    # Remove thinking tags
    content = re.sub(
        r"<think>.*?</think>",
        "",
        content,
        flags=re.DOTALL | re.IGNORECASE
    ).strip()

    # Remove markdown code fences
    content = re.sub(
        r"^```(?:json)?\s*",
        "",
        content,
        flags=re.IGNORECASE
    )

    content = re.sub(
        r"\s*```$",
        "",
        content
    ).strip()

    return content


# =========================================================
# EXTRACT JSON ARRAY
# =========================================================

def extract_json_array(content):

    content = clean_ai_response(content)

    if not content:

        raise ValueError(
            "Nemotron returned an empty response."
        )

    # Direct JSON
    try:

        data = json.loads(content)

        if isinstance(data, list):
            return data

        if isinstance(data, dict):

            for key in [
                "questions",
                "quiz",
                "data",
                "items"
            ]:

                if isinstance(data.get(key), list):
                    return data[key]

    except json.JSONDecodeError:
        pass


    # Find JSON array
    start = content.find("[")

    if start == -1:

        raise ValueError(
            "Nemotron response does not contain a JSON array."
        )


    # Try different endings
    for end in range(
        len(content),
        start,
        -1
    ):

        candidate = content[start:end].strip()

        if not candidate.endswith("]"):
            continue

        try:

            data = json.loads(candidate)

            if isinstance(data, list):
                return data

        except json.JSONDecodeError:
            continue


    raise ValueError(
        "Nemotron returned invalid JSON."
    )


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
            question.get(
                "question",
                ""
            )
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

            answer = str(
                question.get(
                    "answer",
                    ""
                )
            ).strip()


            if not isinstance(options, list):
                continue


            options = [
                str(option).strip()
                for option in options
                if str(option).strip()
            ]


            # Remove duplicates
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
        # FILL IN THE BLANK
        # =====================================================

        elif question_type == "fill_blank":

            answer = str(
                question.get(
                    "answer",
                    ""
                )
            ).strip()


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

            answer = str(
                question.get(
                    "answer",
                    ""
                )
            ).strip()


            if not answer:
                continue


            cleaned.append({

                "type": "short_answer",

                "question": question_text,

                "answer": answer

            })


        # =====================================================
        # TRUE / FALSE
        # =====================================================

        elif question_type == "true_false":

            answer = str(
                question.get(
                    "answer",
                    ""
                )
            ).strip().casefold()


            if answer not in [
                "true",
                "false"
            ]:
                continue


            final_answer = (
                "True"
                if answer == "true"
                else "False"
            )


            cleaned.append({

                "type": "true_false",

                "question": question_text,

                "options": [
                    "True",
                    "False"
                ],

                "answer": final_answer

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
                    pair.get(
                        "left",
                        ""
                    )
                ).strip()


                right = str(
                    pair.get(
                        "right",
                        ""
                    )
                ).strip()


                if left and right:

                    cleaned_pairs.append({

                        "left": left,

                        "right": right

                    })


            if len(cleaned_pairs) < 2:
                continue


            right_options = [
                pair["right"]
                for pair in cleaned_pairs
            ]

            random.shuffle(right_options)


            cleaned.append({

                "type": "match_pairs",

                "question": question_text,

                "pairs": cleaned_pairs,

                "right_options": right_options,

                "answer": cleaned_pairs

            })


    if not cleaned:

        raise ValueError(
            "Nemotron did not return usable questions."
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

    MAX_PDF_CHARS = 30000


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
SOURCE: UPLOADED PDF

Create questions ONLY from the PDF content.

Do not use unrelated information.

PDF CONTENT:
-------------------------
{pdf_content}
-------------------------
"""

    else:

        source_instruction = f"""
SOURCE: TOPIC

Create questions about:

{topic}
"""


    # =====================================================
    # QUESTION TYPE
    # =====================================================

    if question_type == "mcq":

        type_instruction = """
QUESTION TYPE: MCQ

Each object must contain:

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

Rules:
- Exactly 4 options.
- Exactly 1 correct answer.
- Answer must exactly match one option.
"""


    elif question_type == "fill_blank":

        type_instruction = """
QUESTION TYPE: FILL IN THE BLANK

Each object must contain:

{
  "question": "The process of ______ occurs in plants.",
  "answer": "photosynthesis"
}

Rules:
- Question must contain a blank.
- Answer must be the missing word or phrase.
"""


    elif question_type == "short_answer":

        type_instruction = """
QUESTION TYPE: SHORT ANSWER

Each object must contain:

{
  "question": "What is photosynthesis?",
  "answer": "The process by which plants make food using light energy."
}

Rules:
- Keep answers concise.
"""


    elif question_type == "true_false":

        type_instruction = """
QUESTION TYPE: TRUE OR FALSE

Each object must contain:

{
  "question": "Photosynthesis occurs in plants.",
  "answer": "True"
}

Rules:
- Answer must be exactly True or False.
"""


    elif question_type == "match_pairs":

        type_instruction = """
QUESTION TYPE: MATCH PAIRS

Each object must contain:

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
  ]
}

Rules:
- Prefer 4 pairs.
- Each left item has exactly one correct right item.
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

TOPIC:
{topic}

DIFFICULTY:
{difficulty}

{source_instruction}

{type_instruction}

STRICT OUTPUT RULES:

1. Return ONLY a valid JSON array.
2. Start the response with [.
3. End the response with ].
4. Do not write explanations.
5. Do not write Markdown.
6. Do not use code fences.
7. Use double quotes.
8. Do not use trailing commas.
9. Do not repeat questions.
10. Keep questions accurate.
11. If PDF content is supplied, use ONLY the PDF.
12. Generate exactly {question_count} question objects.
"""


    # =====================================================
    # NVIDIA API CALL
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

            temperature=0,

            max_tokens=8000,

            stream=False,

            extra_body={
                "chat_template_kwargs": {
                    "enable_thinking": False
                }
            }

        )

    except Exception as e:

        print(
            "NVIDIA FULL ERROR:",
            repr(e)
        )

        raise RuntimeError(
            f"NVIDIA API error: {e}"
        )
            # =====================================================
    # READ NVIDIA RESPONSE
    # =====================================================

    try:
        content = response.choices[0].message.content

    except Exception:
        raise RuntimeError(
            "Could not read the response from Nemotron."
        )

    if not content:
        raise RuntimeError(
            "Nemotron returned an empty response."
        )


    # =====================================================
    # READ RESPONSE
    # =====================================================

    try:

        content = (
            response
            .choices[0]
            .message
            .content
        )

    except Exception as e:

        raise RuntimeError(
            f"Could not read NVIDIA response: {e}"
        )


    if not content:

        raise RuntimeError(
            "Nemotron returned an empty response."
        )


    print(
        "\n========== NEMOTRON RESPONSE ==========\n"
    )

    print(content)

    print(
        "\n========================================\n"
    )


    # =====================================================
    # PARSE JSON
    # =====================================================

    try:

        questions = extract_json_array(
            content
        )

    except Exception as e:

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
# SAVE QUIZ
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
# LOAD QUIZ
# =========================================================

def load_quiz_data(quiz_id):

    if not quiz_id:
        return []


    file_path = os.path.join(

        QUIZ_DATA_FOLDER,

        f"{quiz_id}.json"

    )


    if not os.path.exists(
        file_path
    ):

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


    if question_count < 1:
        question_count = 5


    if question_count > MAX_QUESTIONS:
        question_count = MAX_QUESTIONS


    # =====================================================
    # VALID TYPES
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


        filename = (
            f"{uuid.uuid4().hex}_"
            f"{filename}"
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
    # DEFAULT TOPIC
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

            topic,

            difficulty,

            question_type,

            question_count,

            pdf_text

        )

    except Exception as e:

        print(
            "\nNVIDIA NEMOTRON ERROR:",
            repr(e)
        )


        error_message = str(e)


        try:

            return render_template(

                "error.html",

                error=error_message

            )

        except Exception:

            return (

                f"""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Quiz Generation Error</title>
                </head>

                <body>

                    <h2>Quiz Generation Error</h2>

                    <p>{error_message}</p>

                    <br>

                    <a href="/">Go Back</a>

                </body>
                </html>
                """,

                500

            )


    # =====================================================
    # VERIFY
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
        # NORMAL TYPES
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


            if question_type == "short_answer":

                user_normalized = (

                    user_answer

                    .casefold()

                    .strip(
                        " .,!?;:"
                    )

                )


                correct_normalized = (

                    correct_answer

                    .casefold()

                    .strip(
                        " .,!?;:"
                    )

                )


                is_correct = (

                    user_normalized

                    == correct_normalized

                )

            else:

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
        # RESULTS
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
