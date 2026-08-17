from flask import Flask, render_template, request

app = Flask(__name__)


# =========================================================
# QUIZ DATABASE
# Python, C++, Java, JavaScript, HTML
# =========================================================

quiz_data = {

    # =====================================================
    # PYTHON
    # =====================================================

    "python": [

        {
            "question": "What is Python?",
            "options": [
                "Programming Language",
                "Operating System",
                "Database",
                "Web Browser"
            ],
            "answer": "Programming Language"
        },

        {
            "question": "Who created Python?",
            "options": [
                "Dennis Ritchie",
                "Guido van Rossum",
                "James Gosling",
                "Bjarne Stroustrup"
            ],
            "answer": "Guido van Rossum"
        },

        {
            "question": "Which keyword is used to define a function in Python?",
            "options": [
                "function",
                "def",
                "fun",
                "define"
            ],
            "answer": "def"
        },

        {
            "question": "Which symbol is used for comments in Python?",
            "options": [
                "//",
                "#",
                "/*",
                "--"
            ],
            "answer": "#"
        },

        {
            "question": "Which data type is used for True or False?",
            "options": [
                "int",
                "str",
                "bool",
                "float"
            ],
            "answer": "bool"
        },

        {
            "question": "Which loop is commonly used to iterate over a sequence?",
            "options": [
                "for",
                "repeat",
                "loop",
                "iterate"
            ],
            "answer": "for"
        },

        {
            "question": "Which function is used to display output in Python?",
            "options": [
                "display()",
                "echo()",
                "print()",
                "show()"
            ],
            "answer": "print()"
        },

        {
            "question": "Which collection is ordered and changeable?",
            "options": [
                "List",
                "Tuple",
                "Set",
                "String"
            ],
            "answer": "List"
        },

        {
            "question": "Which keyword is used to create a class?",
            "options": [
                "object",
                "class",
                "struct",
                "new"
            ],
            "answer": "class"
        },

        {
            "question": "Which file extension is normally used for Python programs?",
            "options": [
                ".java",
                ".cpp",
                ".py",
                ".html"
            ],
            "answer": ".py"
        }
    ],


    # =====================================================
    # C++
    # =====================================================

    "c++": [

        {
            "question": "What is C++?",
            "options": [
                "Programming Language",
                "Operating System",
                "Database",
                "Web Browser"
            ],
            "answer": "Programming Language"
        },

        {
            "question": "Who developed C++?",
            "options": [
                "James Gosling",
                "Bjarne Stroustrup",
                "Guido van Rossum",
                "Dennis Ritchie"
            ],
            "answer": "Bjarne Stroustrup"
        },

        {
            "question": "Which function is the entry point of a C++ program?",
            "options": [
                "start()",
                "run()",
                "main()",
                "begin()"
            ],
            "answer": "main()"
        },

        {
            "question": "Which symbol is used to end a statement in C++?",
            "options": [
                ".",
                ",",
                ";",
                ":"
            ],
            "answer": ";"
        },

        {
            "question": "Which header is commonly used for input and output in modern C++?",
            "options": [
                "iostream",
                "stdio",
                "input",
                "output"
            ],
            "answer": "iostream"
        },

        {
            "question": "Which concept allows a class to inherit another class?",
            "options": [
                "Inheritance",
                "Compilation",
                "Iteration",
                "Casting"
            ],
            "answer": "Inheritance"
        },

        {
            "question": "Which keyword is used to create an object dynamically?",
            "options": [
                "create",
                "malloc",
                "new",
                "object"
            ],
            "answer": "new"
        },

        {
            "question": "Which OOP concept means hiding internal implementation details?",
            "options": [
                "Inheritance",
                "Encapsulation",
                "Looping",
                "Compilation"
            ],
            "answer": "Encapsulation"
        },

        {
            "question": "Which file extension is commonly used for C++ source files?",
            "options": [
                ".py",
                ".java",
                ".cpp",
                ".html"
            ],
            "answer": ".cpp"
        },

        {
            "question": "Which operator is used with cout for output?",
            "options": [
                "<<",
                ">>",
                "==",
                "&&"
            ],
            "answer": "<<"
        }
    ],


    # =====================================================
    # JAVA
    # =====================================================

    "java": [

        {
            "question": "What is Java?",
            "options": [
                "Programming Language",
                "Database",
                "Operating System",
                "Web Browser"
            ],
            "answer": "Programming Language"
        },

        {
            "question": "Who originally developed Java?",
            "options": [
                "James Gosling",
                "Bjarne Stroustrup",
                "Guido van Rossum",
                "Dennis Ritchie"
            ],
            "answer": "James Gosling"
        },

        {
            "question": "Which keyword is used to create a class in Java?",
            "options": [
                "class",
                "ClassName",
                "define",
                "struct"
            ],
            "answer": "class"
        },

        {
            "question": "Which method is the entry point of a Java application?",
            "options": [
                "start()",
                "main()",
                "run()",
                "execute()"
            ],
            "answer": "main()"
        },

        {
            "question": "Which keyword is used to inherit a class?",
            "options": [
                "inherits",
                "extends",
                "implements",
                "inherit"
            ],
            "answer": "extends"
        },

        {
            "question": "Which keyword is used to create an object?",
            "options": [
                "object",
                "create",
                "new",
                "make"
            ],
            "answer": "new"
        },

        {
            "question": "Which data type stores whole numbers?",
            "options": [
                "float",
                "int",
                "boolean",
                "char"
            ],
            "answer": "int"
        },

        {
            "question": "Which keyword is used to define a constant variable?",
            "options": [
                "constant",
                "const",
                "final",
                "static"
            ],
            "answer": "final"
        },

        {
            "question": "Java source files normally have which extension?",
            "options": [
                ".py",
                ".cpp",
                ".java",
                ".js"
            ],
            "answer": ".java"
        },

        {
            "question": "Java is strongly associated with which programming concept?",
            "options": [
                "Object-Oriented Programming",
                "Only procedural programming",
                "Only markup",
                "Only database programming"
            ],
            "answer": "Object-Oriented Programming"
        }
    ],


    # =====================================================
    # JAVASCRIPT
    # =====================================================

    "javascript": [

        {
            "question": "What is JavaScript mainly used for?",
            "options": [
                "Making web pages interactive",
                "Creating only databases",
                "Operating systems only",
                "Writing hardware drivers only"
            ],
            "answer": "Making web pages interactive"
        },

        {
            "question": "Which keyword can declare a block-scoped variable?",
            "options": [
                "let",
                "define",
                "varname",
                "integer"
            ],
            "answer": "let"
        },

        {
            "question": "Which keyword declares a variable that cannot be reassigned?",
            "options": [
                "fixed",
                "constant",
                "const",
                "final"
            ],
            "answer": "const"
        },

        {
            "question": "Which function displays a message in the browser console?",
            "options": [
                "print()",
                "console.log()",
                "display()",
                "writeConsole()"
            ],
            "answer": "console.log()"
        },

        {
            "question": "Which symbol is used for a single-line comment?",
            "options": [
                "#",
                "//",
                "<!--",
                "**"
            ],
            "answer": "//"
        },

        {
            "question": "Which operator checks strict equality?",
            "options": [
                "=",
                "==",
                "===",
                "!="
            ],
            "answer": "==="
        },

        {
            "question": "Which keyword is used to define a function?",
            "options": [
                "function",
                "def",
                "func",
                "method"
            ],
            "answer": "function"
        },

        {
            "question": "Which extension is commonly used for JavaScript files?",
            "options": [
                ".java",
                ".js",
                ".py",
                ".cpp"
            ],
            "answer": ".js"
        },

        {
            "question": "Which method adds an item to the end of an array?",
            "options": [
                "push()",
                "addEnd()",
                "insert()",
                "appendEnd()"
            ],
            "answer": "push()"
        },

        {
            "question": "Which language is JavaScript primarily executed by in a web browser?",
            "options": [
                "Browser JavaScript engine",
                "HTML engine only",
                "SQL engine",
                "C compiler"
            ],
            "answer": "Browser JavaScript engine"
        }
    ],


    # =====================================================
    # HTML
    # =====================================================

    "html": [

        {
            "question": "What does HTML stand for?",
            "options": [
                "Hyper Text Markup Language",
                "High Text Machine Language",
                "Hyper Tool Multi Language",
                "Home Text Markup Language"
            ],
            "answer": "Hyper Text Markup Language"
        },

        {
            "question": "Which tag is used for the largest heading?",
            "options": [
                "<h1>",
                "<heading>",
                "<head>",
                "<h6>"
            ],
            "answer": "<h1>"
        },

        {
            "question": "Which tag creates a paragraph?",
            "options": [
                "<paragraph>",
                "<p>",
                "<para>",
                "<text>"
            ],
            "answer": "<p>"
        },

        {
            "question": "Which tag creates a hyperlink?",
            "options": [
                "<link>",
                "<a>",
                "<href>",
                "<url>"
            ],
            "answer": "<a>"
        },

        {
            "question": "Which attribute specifies the destination of a hyperlink?",
            "options": [
                "src",
                "href",
                "link",
                "url"
            ],
            "answer": "href"
        },

        {
            "question": "Which tag is used to display an image?",
            "options": [
                "<image>",
                "<img>",
                "<picture>",
                "<src>"
            ],
            "answer": "<img>"
        },

        {
            "question": "Which tag creates an unordered list?",
            "options": [
                "<ol>",
                "<ul>",
                "<list>",
                "<li>"
            ],
            "answer": "<ul>"
        },

        {
            "question": "Which tag creates a numbered list?",
            "options": [
                "<ul>",
                "<ol>",
                "<li>",
                "<number>"
            ],
            "answer": "<ol>"
        },

        {
            "question": "Which tag is used to create a form?",
            "options": [
                "<input>",
                "<form>",
                "<data>",
                "<field>"
            ],
            "answer": "<form>"
        },

        {
            "question": "Which file extension is commonly used for HTML files?",
            "options": [
                ".html",
                ".ht",
                ".web",
                ".page"
            ],
            "answer": ".html"
        }
    ]
}


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():
    return render_template("index.html")


# =========================================================
# START QUIZ
# =========================================================

@app.route("/quiz", methods=["POST"])
def quiz():

    topic = request.form.get("topic", "").strip().lower()

    if topic not in quiz_data:

        return render_template(
            "index.html",
            error="Please enter Python, C++, Java, JavaScript or HTML."
        )

    questions = quiz_data[topic]

    return render_template(
        "quiz.html",
        quiz=questions,
        topic=topic
    )


# =========================================================
# RESULT
# =========================================================

@app.route("/result", methods=["POST"])
def result():

    topic = request.form.get("topic", "").strip().lower()

    if topic not in quiz_data:
        return "Invalid topic"

    questions = quiz_data[topic]

    score = 0
    total = len(questions)

    for i in range(total):

        user_answer = request.form.get(f"q{i}")

        if user_answer == questions[i]["answer"]:
            score += 1

    percentage = (score / total) * 100

    if percentage >= 80:
        feedback = "Excellent! 🔥"

    elif percentage >= 60:
        feedback = "Very Good! 👏"

    elif percentage >= 40:
        feedback = "Good, but you can improve! 👍"

    else:
        feedback = "Need Improvement! 📚"

    return render_template(
        "result.html",
        score=score,
        total=total,
        percentage=round(percentage, 2),
        feedback=feedback,
        topic=topic
    )


# =========================================================
# RUN APP
# =========================================================

if __name__ == "__main__":
    app.run(debug=True)