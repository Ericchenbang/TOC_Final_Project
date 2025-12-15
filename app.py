from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import json
import os
import re
import random

app = Flask(__name__)
app.secret_key = "hangman-secret-key"

# root directory
@app.route('/')
def index():
    return render_template('index.html')
    
#--------------------------------------------------------------#
#--------------------------------------------------------------#

# watch news
@app.route('/news', methods=['POST'])
def news():
    #session['cefr'] = request.form.get('cefr')
    #session['count'] = int(request.form.get('count'))
    category = request.form.get('news_type')
    return redirect(url_for('news_list', category=category))

@app.route('/news/<category>')
def news_list(category):
    news_path = f"data/news/{category}.json"

    with open(news_path, 'r', encoding='utf-8') as f:
        news_data = json.load(f)

    return render_template(
        'news_list.html',
        category=category,
        articles=news_data["articles"]
    )


@app.route('/news/<category>/<int:article_id>')
def news_detail(category, article_id):
    news_path = f"data/news/{category}.json"

    with open(news_path, 'r', encoding='utf-8') as f:
        news_data = json.load(f)

    # find coresponding id article
    article = next(
        (a for a in news_data["articles"] if a["id"] == article_id),
        None
    )

    if article is None:
        return "Article not found", 404

    return render_template(
        'news_detail.html',
        category=category,
        article=article
    )

#--------------------------------------------------------------#
#--------------------------------------------------------------#
@app.route('/mindmap')
def mindmap():
    with open('data/mindMap.json', 'r', encoding='utf-8') as f:
        mindmap_data = json.load(f)

    return render_template(
        'mindmap.html',
        mindmap=mindmap_data
    )

#--------------------------------------------------------------#
#--------------------------------------------------------------#
@app.route('/reading', methods=['GET'])
def reading():
    with open('data/reading.json', 'r', encoding='utf-8') as f:
        questions = json.load(f)

    return render_template(
        'reading.html',
        questions=questions,
        result=None
    )

@app.route('/submit_reading', methods=['POST'])
def submit_reading():
    with open('data/reading.json', 'r', encoding='utf-8') as f:
        questions = json.load(f)

    result = {}

    for q in questions:
        qid = q["id"]

        if q["type"] == "True_Or_False":
            user_answer = request.form.get(qid)
            correct = str(q["answer"]).lower()

            is_correct = (user_answer == correct)

            result[qid] = {
                "type": q["type"],
                "user": user_answer,
                "is_correct": is_correct,
                "explanation": q["explanation"]
            }

        else:  # Multiple_Answer
            user_choices = request.form.getlist(qid)
            correct_choices = [str(i) for i in q["correct_choices"]]

            is_correct = sorted(user_choices) == sorted(correct_choices)

            result[qid] = {
                "type": q["type"],
                "user": user_choices,
                "correct": correct_choices,
                "is_correct": is_correct,
                "explanation": q["explanation"]
            }

    return render_template(
        'reading.html',
        questions=questions,
        result=result
    )





#--------------------------------------------------------------#
#--------------------------------------------------------------#
@app.route('/start_learn', methods=['POST'])
def start_learn():
    session['cefr'] = request.form.get('cefr')
    session['count'] = int(request.form.get('count'))

    return redirect(url_for('learn'))


@app.route('/learn', methods=['GET'])
def learn():
    level = session.get('cefr')
    count = session.get('count')

    # the file received
    json_path = os.path.join('data/vocabulary', 'words.json')

    with open(json_path, 'r', encoding='utf-8') as f:
        words = json.load(f)

    # choose the number of voc 
    selected = words[:count]

    return render_template(
        'vocabulary.html', 
        words = selected,
        level = level,
        feedback = {}
    )


#--------------------------------------------------------------#
#--------------------------------------------------------------#

# use vocabulary make sentence
@app.route('/check_sentence', methods=['POST'])
def check_sentence():
    word = request.form.get('word')
    sentence = request.form.get('sentence')
    level = request.form.get('level')
    count = int(request.form.get('count'))

    # mock reply
    mock_result = {
        "word": word,
        "user_sentence": sentence,
        "is_correct": False if "bad" in sentence else True,
        "explanation": "Example, false if bad inside"
    }

    # load vocabulary
    json_path = os.path.join('data/vocabulary', 'words.json')
    with open(json_path, 'r', encoding='utf-8') as f:
        all_words = json.load(f)

    words = all_words[:count]

    # not redirect, add anchor
    return render_template(
        'vocabulary.html',
        words=words,
        level=level,
        feedback={word: mock_result},
        anchor=word   # use for scroll 
    )

#--------------------------------------------------------------#
#--------------------------------------------------------------#

# Cloze 
@app.route('/cloze', methods=['GET'])
def cloze():
    # read voc
    with open('data/vocabulary/words.json', 'r', encoding='utf-8') as f:
        words = json.load(f)

    return render_template(
        'cloze.html',
        stage="select",
        words=words
    )

@app.route('/cloze_select', methods=['POST'])
def cloze_select():
    selected_words = request.form.getlist('words')

    # if user choose less than 2
    if len(selected_words) < 2:
        with open('data/vocabulary/words.json', 'r', encoding='utf-8') as f:
            words = json.load(f)

        return render_template(
            'cloze.html',
            stage="select",
            words=words,
            error="Please select at least TWO words to start the cloze test."
        )

    data = [{"word": w} for w in selected_words]

    with open('data/cloze/input.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # show cloze article
    return redirect('/cloze_play')


@app.route('/cloze_play', methods=['GET'])
def cloze_play():
    # read cloze json
    with open('data/cloze/cloze.json', 'r', encoding='utf-8') as f:
        cloze_data = json.load(f)

    text = cloze_data["question"]

    # read input.json
    with open('data/cloze/input.json', 'r', encoding='utf-8') as f:
        selected_words = json.load(f)

    def replace_blank(match):
        idx = match.group(1)
        return f'<input type="text" name="blank_{idx}" style="width:120px;">'

    html_text = re.sub(r'___\[(\d+)\]___', replace_blank, text)

    return render_template(
        'cloze.html',
        stage="play",
        cloze_text=html_text,
        selected_words=selected_words,
        result=None
    )

@app.route('/submit_cloze', methods=['POST'])
def submit_cloze():
    # read cloze json
    with open('data/cloze/cloze.json', 'r', encoding='utf-8') as f:
        cloze_data = json.load(f)

    text = cloze_data["question"]

    # turn ans list into dict: { "1": "reaction", ... }
    answers = {
        str(item["idx"]): item["word"]
        for item in cloze_data["ans"]
    }

    # read voc chosen by user
    with open('data/cloze/input.json', 'r', encoding='utf-8') as f:
        selected_words = json.load(f)

    used_words = set(request.form.getlist('used_word'))

    result = {}

    for key, value in request.form.items():
        idx = key.replace('blank_', '')
        user = value.strip()
        correct = answers.get(idx, "")

        is_correct = user.lower() == correct.lower()
        result[idx] = {
            "user": user,
            "correct": correct,
            "is_correct": user.lower() == correct.lower()
        }
        if is_correct and correct:
            used_words.add(correct)

    def replace_blank(match):
        idx = match.group(1)
        r = result.get(idx)

        if not r:
            return f'<input type="text" name="blank_{idx}" style="width:120px;">'

        color = "#c8f7c5" if r["is_correct"] else "#f7c5c5"
        readonly = "readonly" if r["is_correct"] else ""
        return f'''
        <input type="text"
               name="blank_{idx}"
               value="{r['user']}"
               {readonly}
               style="width:120px; background-color:{color};">
        '''
    locked_words = {
        r["correct"] for r in result.values() if r["is_correct"]
    }

    html_text = re.sub(r'___\[(\d+)\]___', replace_blank, text)

    return render_template(
        'cloze.html',
        stage="play",
        cloze_text=html_text,
        selected_words=selected_words,
        used_words=list(used_words),
        locked_words=locked_words,
        result=result
    )

#--------------------------------------------------------------#
#--------------------------------------------------------------#
## Hangman Game ###
@app.route('/hangman', methods=['GET'])
def hangman():
    # read vocabulary
    with open('data/vocabulary/words.json', 'r', encoding='utf-8') as f:
        words = json.load(f)

    answer = random.choice(words)["word"].lower()

    session["hangman_answer"] = answer
    session["hangman_guessed"] = []
    session["hangman_wrong"] = 0
    session["hangman_hint_used"] = False


    masked = " ".join("_" for _ in answer)

    return render_template(
        'hangman.html',
        masked=masked,
        guessed=[],
        wrong=0,
        win=False,
        lose=False
    )


@app.route('/hangman_guess_ajax', methods=['POST'])
def hangman_guess_ajax():
    data = request.json
    letter = data.get("letter", "").lower()

    answer = session.get("hangman_answer")
    guessed = session.get("hangman_guessed", [])
    wrong = session.get("hangman_wrong", 0)

    if not letter or len(letter) != 1 or not letter.isalpha():
        return jsonify({"error": "invalid input"})

    if letter not in guessed:
        guessed.append(letter)
        if letter not in answer:
            wrong += 1

    session["hangman_guessed"] = guessed
    session["hangman_wrong"] = wrong
    

    masked = " ".join(c if c in guessed else "_" for c in answer)

    win = "_" not in masked
    lose = wrong >= 6

    return jsonify({
        "masked": masked,
        "guessed": guessed,
        "wrong": wrong,
        "win": win,
        "lose": lose,
        "answer": answer if lose else None
    })


@app.route('/hangman_hint', methods=['POST'])
def hangman_hint():
    # The user had used the hint
    if session.get("hangman_hint_used"):
        return jsonify({
            "error": "hint_used",
            "wrong": session.get("hangman_wrong", 0)
        })

    # noted as used
    session["hangman_hint_used"] = True

    # minus one life
    wrong = session.get("hangman_wrong", 0) + 1
    session["hangman_wrong"] = wrong

    with open('data/hangman/describe.txt', 'r', encoding='utf-8') as f:
        hint_text = f.read()

    lose = wrong >= 6

    return jsonify({
        "hint": hint_text,
        "wrong": wrong,
        "lose": lose
    })



if __name__ == '__main__':
    app.run(debug=True)
